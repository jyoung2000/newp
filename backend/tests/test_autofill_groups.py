"""A realistic employment-history + references form, filled end to end.

The unit tests in test_groups.py pin detection and resolution. This one goes
through the HTTP API the extension actually calls, with two employers and three
references entered the way a user would enter them, against a form shaped the
way ATS employment sections are shaped — repeated blocks, indexed names, and a
reference section whose blocks aren't numbered at all.
"""
from __future__ import annotations

from tests.conftest import register_and_login


def _setup(client) -> dict:
    headers = register_and_login(client, "grouped@example.com")
    client.put(
        "/api/profile",
        json={"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com",
              "phone": "+1 555 0100", "over_18": True},
        headers=headers,
    )
    # Two roles, most recent first — the order the UI tells the user matters.
    for job in [
        {
            "title": "Staff Engineer",
            "company": "Analytical Engines Ltd",
            "location": "London",
            "start_date": "2021-04-01",
            "is_current": True,
            "manager_name": "Charles Babbage",
            "manager_title": "Director of Engines",
            "manager_email": "charles@engines.example",
            "manager_phone": "+44 20 7000 0001",
            "may_contact_employer": True,
            "summary": "Owned the program tables and the difference engine's test suite.",
        },
        {
            "title": "Junior Analyst",
            "company": "Somerville & Co",
            "location": "Bath",
            "start_date": "2018-01-15",
            "end_date": "2021-03-31",
            "is_current": False,
            "manager_name": "Mary Somerville",
            "manager_title": "Principal",
            "manager_email": "mary@somerville.example",
            "manager_phone": "+44 20 7000 0002",
            "may_contact_employer": False,
            "reason_for_leaving": "Offered a larger role elsewhere",
            "summary": "Computed tables by hand and checked others' arithmetic.",
        },
    ]:
        r = client.post("/api/profile/work-experiences", json=job, headers=headers)
        assert r.status_code in (200, 201), r.text

    for ref in [
        {"name": "Mary Somerville", "relationship_to_user": "Former manager",
         "company": "Somerville & Co", "title": "Principal", "email": "mary@rs.example",
         "phone": "+44 20 7000 0010", "years_known": 7, "reference_type": "professional",
         "may_contact": True},
        {"name": "Augustus De Morgan", "relationship_to_user": "Former tutor",
         "company": "University College", "title": "Professor",
         "email": "augustus@ucl.example", "phone": "+44 20 7000 0011", "years_known": 10,
         "reference_type": "professional", "may_contact": True},
        {"name": "Annabella Byron", "relationship_to_user": "Family friend",
         "company": "—", "email": "anna@example.com", "phone": "+44 20 7000 0012",
         "years_known": 30, "reference_type": "personal", "may_contact": False},
    ]:
        r = client.post("/api/profile/recommendations", json=ref, headers=headers)
        assert r.status_code in (200, 201), r.text

    code = client.post("/api/devices/pairing-code", headers=headers).json()["code"]
    token = client.post(
        "/api/ext/pair",
        json={"code": code, "name": "Chrome", "browser": "chrome", "extension_version": "0.1.0"},
    ).json()["token"]
    return {"authorization": f"Bearer {token}"}


def _f(ref, label, name=None, surrounding="", field_type="text"):
    return {
        "ref": ref, "label": label, "field_type": field_type, "options": [],
        "required": False, "name": name, "surrounding_text": surrounding,
    }


def _autofill(client, device, fields):
    """Returns {ref: resolution}. Assertions read `value`; `formatted` is only
    populated where the typed form differs (dates), matching the field
    library — the extension reads `formatted ?? value`."""
    r = client.post(
        "/api/ext/autofill",
        json={"url": "https://careers.example/apply", "title": "Application", "fields": fields},
        headers=device,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    return {x["ref"]: x for x in body["resolutions"]}, body


def test_two_employer_blocks_with_indexed_names(client):
    """The shape a real ATS posts: work_history[0][…] and work_history[1][…]."""
    device = _setup(client)
    fields = []
    for i in (0, 1):
        fields += [
            _f(f"c{i}", "Company", f"work_history[{i}][company]"),
            _f(f"t{i}", "Job title", f"work_history[{i}][title]"),
            _f(f"s{i}", "Supervisor name", f"work_history[{i}][supervisor]"),
            _f(f"sp{i}", "Supervisor phone", f"work_history[{i}][supervisor_phone]"),
            _f(f"from{i}", "From", f"work_history[{i}][start_date]", field_type="date"),
            _f(f"to{i}", "To", f"work_history[{i}][end_date]", field_type="date"),
            _f(f"rl{i}", "Reason for leaving", f"work_history[{i}][reason]"),
            _f(f"d{i}", "Duties", f"work_history[{i}][duties]", field_type="textarea"),
        ]
    got, body = _autofill(client, device, fields)

    assert got["c0"]["value"] == "Analytical Engines Ltd"
    assert got["t0"]["value"] == "Staff Engineer"
    assert got["s0"]["value"] == "Charles Babbage"
    assert got["sp0"]["value"] == "+44 20 7000 0001"
    assert got["from0"]["value"] == "2021-04-01"
    # A role the user still holds: "Present", not a blank or an invented date.
    assert got["to0"]["value"] == "Present"
    assert got["d0"]["value"].startswith("Owned the program tables")

    assert got["c1"]["value"] == "Somerville & Co"
    assert got["t1"]["value"] == "Junior Analyst"
    assert got["s1"]["value"] == "Mary Somerville"
    assert got["to1"]["value"] == "2021-03-31"
    assert got["rl1"]["value"] == "Offered a larger role elsewhere"

    # The current role has no reason for leaving, so that one field asks.
    assert got["rl0"]["status"] == "needs_human"
    assert "employer 1" in got["rl0"]["reason"].lower()
    assert body["needs_human"] == 1


def test_three_unnumbered_reference_blocks_fill_three_different_people(client):
    """Nothing in these fields says which reference they belong to — only the
    order they appear in. Getting this wrong fills the same person three times."""
    device = _setup(client)
    fields = []
    for i in range(3):
        fields += [
            _f(f"n{i}", "Name", "ref_name", "References"),
            _f(f"r{i}", "Relationship", "ref_rel", "References"),
            _f(f"e{i}", "Email", "ref_email", "References"),
            _f(f"p{i}", "Phone", "ref_phone", "References"),
        ]
    got, _ = _autofill(client, device, fields)

    assert [got[f"n{i}"]["value"] for i in range(3)] == [
        "Mary Somerville",
        "Augustus De Morgan",
        "Annabella Byron",
    ]
    assert [got[f"e{i}"]["value"] for i in range(3)] == [
        "mary@rs.example",
        "augustus@ucl.example",
        "anna@example.com",
    ]
    assert got["r2"]["value"] == "Family friend"


def test_the_applicants_own_details_are_untouched_by_the_group_layer(client):
    """The whole form at once: the applicant's own contact block and a
    reference block, side by side. Each must get its own person's details."""
    device = _setup(client)
    got, _ = _autofill(
        client,
        device,
        [
            _f("me_first", "First name", "first_name"),
            _f("me_email", "Email", "email"),
            _f("me_phone", "Phone", "phone"),
            _f("ref_name", "Reference 1 name", "references[0][name]"),
            _f("ref_email", "Reference 1 email", "references[0][email]"),
            _f("ref_phone", "Reference 1 phone", "references[0][phone]"),
        ],
    )
    assert got["me_first"]["value"] == "Ada"
    assert got["me_email"]["value"] == "ada@example.com"
    assert got["me_phone"]["value"] == "+1 555 0100"
    assert got["ref_name"]["value"] == "Mary Somerville"
    assert got["ref_email"]["value"] == "mary@rs.example"
    assert got["ref_phone"]["value"] == "+44 20 7000 0010"


def test_may_contact_answers_yes_and_no_per_employer(client):
    """A boolean the user set differently on two jobs. 'No' is a real answer and
    must not be silently turned into 'yes'."""
    device = _setup(client)
    got, _ = _autofill(
        client,
        device,
        [
            _f("mc0", "May we contact this employer?", "employer_1_may_contact",
               field_type="radio"),
            _f("mc1", "May we contact this employer?", "employer_2_may_contact",
               field_type="radio"),
        ],
    )
    assert got["mc0"]["value"] is True
    assert got["mc1"]["value"] is False


def test_a_fourth_employer_block_asks_instead_of_inventing_one(client):
    """The user has two jobs; the form has room for four. The empty blocks must
    ask, not repeat the last job or make something up."""
    device = _setup(client)
    got, body = _autofill(
        client,
        device,
        [
            _f("c2", "Company", "work_history[2][company]"),
            _f("s2", "Supervisor", "work_history[2][supervisor]"),
        ],
    )
    assert got["c2"]["status"] == "needs_human"
    assert got["s2"]["status"] == "needs_human"
    assert "employer 3" in got["c2"]["reason"].lower()
    assert body["filled"] == 0


def test_group_answers_say_where_they_came_from(client):
    """A user reviewing a fill needs to see which entry a value came from."""
    device = _setup(client)
    got, _ = _autofill(
        client, device, [_f("s", "Employer 2 supervisor name", "employer_2_supervisor")]
    )
    assert got["s"]["value"] == "Mary Somerville"
    assert got["s"]["source"] == "profile"
    assert "employer 2" in got["s"]["reason"].lower()
    assert got["s"]["field_key"] == "employer.manager_name"


def test_group_fields_survive_a_backup_round_trip(client):
    """These are new columns; an export that quietly dropped them would lose
    exactly the data this feature exists to store."""
    import io

    device = _setup(client)
    assert device  # setup ran
    headers = client.post(
        "/api/auth/login", json={"email": "grouped@example.com", "password": "correct horse 9!"}
    ).json()
    headers = {"x-csrf-token": headers["csrf_token"]}

    backup = client.get("/api/transfer/everything.zip", headers=headers).content
    target = register_and_login(client, "restored@example.com")
    r = client.post(
        "/api/transfer/backup/restore",
        files={"file": ("b.zip", io.BytesIO(backup), "application/zip")},
        headers=target,
    )
    assert r.status_code == 200, r.text

    profile = client.get("/api/profile", headers=target).json()
    jobs = sorted(profile["work_experiences"], key=lambda w: w["order_index"])
    assert jobs[0]["manager_name"] == "Charles Babbage"
    assert jobs[0]["manager_email"] == "charles@engines.example"
    assert jobs[0]["may_contact_employer"] is True
    assert jobs[1]["reason_for_leaving"] == "Offered a larger role elsewhere"
    assert jobs[1]["may_contact_employer"] is False
    assert jobs[1]["summary"].startswith("Computed tables")

    refs = profile["recommendations"]
    assert {r["name"] for r in refs} == {"Mary Somerville", "Augustus De Morgan", "Annabella Byron"}
    by_name = {r["name"]: r for r in refs}
    assert by_name["Mary Somerville"]["email"] == "mary@rs.example"
    assert by_name["Mary Somerville"]["years_known"] == 7
    assert by_name["Annabella Byron"]["reference_type"] == "personal"
    assert by_name["Annabella Byron"]["may_contact"] is False
