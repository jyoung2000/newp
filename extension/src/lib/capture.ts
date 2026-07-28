// Describes the job page the user is personally looking at, so they can save
// it with one click. Strictly read-only: it inspects the DOM their own
// browser already rendered and never clicks, fills, navigates, mutates or
// fetches anything. Nothing here runs on its own — the user presses the
// button in the popup.
//
// Three layers, best first: schema.org/JobPosting JSON-LD (the same shape the
// backend's app/sources/jsonld.py understands), then OpenGraph/meta tags,
// then generic DOM heuristics.

export type CaptureConfidence = "high" | "medium" | "low";

export interface CapturedJob {
  url: string;
  title: string;
  company: string;
  location: string | null;
  description: string | null;
  salary_raw: string | null;
  apply_url: string | null;
  posted_at_text: string | null;
  confidence: CaptureConfidence;
}

// Field caps mirror the backend's column widths (app/models/search.py).
const MAX_SHORT = 300;
const MAX_URL = 1000;
const MAX_DESCRIPTION = 20000;
// Above this a "company" element is a page wrapper, not a company name.
const MAX_VALUE = 120;

type Json = Record<string, unknown>;

interface Draft {
  title: string | null;
  company: string | null;
  location: string | null;
  description: string | null;
  salary_raw: string | null;
  apply_url: string | null;
  posted_at_text: string | null;
}

const EMPTY: Draft = {
  title: null,
  company: null,
  location: null,
  description: null,
  salary_raw: null,
  apply_url: null,
  posted_at_text: null,
};

function clean(value: unknown, max = MAX_SHORT): string | null {
  if (typeof value === "number") return String(value);
  if (typeof value !== "string") return null;
  const text = value.replace(/\s+/g, " ").trim();
  return text ? text.slice(0, max) : null;
}

function block(value: string | null | undefined): string | null {
  if (!value) return null;
  const lines = value.split("\n").map((line) => line.trim());
  const text = lines.filter(Boolean).join("\n");
  return text ? text.slice(0, MAX_DESCRIPTION) : null;
}

function absolute(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url, location.href).href.slice(0, MAX_URL);
  } catch {
    return null;
  }
}

function stripHtml(value: unknown): string | null {
  if (typeof value !== "string" || !value.trim()) return null;
  if (!value.includes("<")) return block(value);
  // An inert, detached document: the page is never touched and no resource
  // in the markup is loaded.
  const parsed = new DOMParser().parseFromString(value, "text/html");
  return block(parsed.body?.textContent || parsed.documentElement?.textContent);
}

function query(selector: string): HTMLElement[] {
  try {
    return Array.from(document.querySelectorAll<HTMLElement>(selector));
  } catch {
    // Case-insensitive attribute selectors aren't universal; skip quietly.
    return [];
  }
}

function shortText(el: Element | null, max = MAX_VALUE): string | null {
  if (el === null) return null;
  const text = clean((el as HTMLElement).innerText ?? el.textContent, MAX_SHORT);
  return text && text.length <= max ? text : null;
}

/** A value sitting next to a label such as "Company" or "Salary". */
function labelledValue(pattern: RegExp): string | null {
  for (const el of query("dt, th, label, strong, b")) {
    const label = shortText(el, 40);
    if (!label || !pattern.test(label)) continue;
    const value = shortText(el.nextElementSibling);
    if (value && !pattern.test(value)) return value;
  }
  return null;
}

function firstMatch(selectors: string[], max = MAX_VALUE): string | null {
  for (const selector of selectors) {
    for (const el of query(selector)) {
      const value = shortText(el, max);
      if (value) return value;
    }
  }
  return null;
}

// --- a. schema.org/JobPosting JSON-LD --------------------------------------

function collectJobPostings(node: unknown, out: Json[]): void {
  if (Array.isArray(node)) {
    node.forEach((item) => collectJobPostings(item, out));
    return;
  }
  if (!node || typeof node !== "object") return;
  const obj = node as Json;
  const type = obj["@type"];
  const types = Array.isArray(type) ? type : [type];
  if (types.some((t) => t === "JobPosting")) out.push(obj);
  for (const key of ["@graph", "mainEntity", "itemListElement", "item"]) {
    if (key in obj) collectJobPostings(obj[key], out);
  }
}

function jsonLdCompany(posting: Json): string | null {
  const org = posting.hiringOrganization;
  if (typeof org === "string") return clean(org);
  if (org && typeof org === "object") return clean((org as Json).name);
  return null;
}

function jsonLdLocation(posting: Json): string | null {
  const raw = posting.jobLocation;
  const places = Array.isArray(raw) ? raw : [raw];
  const parts: string[] = [];
  for (const place of places) {
    if (!place || typeof place !== "object") continue;
    const address = (place as Json).address;
    if (typeof address === "string") {
      parts.push(address);
    } else if (address && typeof address === "object") {
      const a = address as Json;
      const bits = [a.addressLocality, a.addressRegion, a.addressCountry]
        .map((bit) => clean(bit))
        .filter(Boolean);
      if (bits.length) parts.push(bits.join(", "));
    }
  }
  const text = clean(Array.from(new Set(parts)).join("; "));
  if (text) return text;
  const kind = clean(posting.jobLocationType);
  return kind && /telecommute/i.test(kind) ? "Remote" : null;
}

function jsonLdSalary(posting: Json): string | null {
  const base = posting.baseSalary;
  if (base === null || base === undefined) return null;
  if (typeof base !== "object") return clean(base);
  const obj = base as Json;
  const currency = clean(obj.currency) || "";
  const value = obj.value;
  if (value === null || value === undefined) return null;
  if (typeof value !== "object") return clean(`${currency} ${String(value)}`);
  const v = value as Json;
  const minimum = v.minValue ?? v.value;
  const maximum = v.maxValue ?? v.value;
  const amounts = [minimum, maximum]
    .map((amount) => clean(amount))
    .filter((amount): amount is string => amount !== null);
  const range = Array.from(new Set(amounts)).join(" - ");
  if (!range) return null;
  const unit = clean(v.unitText);
  return clean(`${currency} ${range}${unit ? ` per ${unit.toLowerCase()}` : ""}`);
}

function fromJsonLd(): Draft | null {
  const postings: Json[] = [];
  for (const script of query('script[type="application/ld+json"]')) {
    const raw = script.textContent;
    if (!raw) continue;
    try {
      collectJobPostings(JSON.parse(raw), postings);
    } catch {
      // Some pages embed several objects or trailing commas; skip rather
      // than guess at what they meant.
    }
  }
  for (const posting of postings) {
    const title = clean(posting.title);
    if (!title) continue;
    return {
      title,
      company: jsonLdCompany(posting),
      location: jsonLdLocation(posting),
      description: stripHtml(posting.description),
      salary_raw: jsonLdSalary(posting),
      apply_url: absolute(clean(posting.url, MAX_URL)),
      posted_at_text: clean(posting.datePosted),
    };
  }
  return null;
}

// --- b. OpenGraph / meta tags ---------------------------------------------

function metaContent(selector: string): string | null {
  const el = document.querySelector<HTMLMetaElement>(selector);
  return clean(el?.content, MAX_DESCRIPTION);
}

function fromMeta(): Draft {
  return {
    ...EMPTY,
    title: clean(metaContent('meta[property="og:title"]')),
    description: block(
      metaContent('meta[property="og:description"]') || metaContent('meta[name="description"]'),
    ),
  };
}

// --- c. Generic DOM heuristics --------------------------------------------

const TITLE_SEPARATOR = /\s+[|•·–—‐-]\s+/;
const BOARD_NOISE = /^(?:jobs?|careers?|hiring|vacancies|job\s+application|apply|home)$/i;
const DOMAIN_LIKE = /^[\w-]+(?:\.[\w-]+)+$/;

/** document.title minus the usual " - Jobs at X" / " | Indeed.com" tails. */
function fromDocumentTitle(): { title: string | null; company: string | null } {
  const parts = (document.title || "")
    .split(TITLE_SEPARATOR)
    .map((part) => part.trim())
    .filter(Boolean);
  let company: string | null = null;
  const kept: string[] = [];
  for (const part of parts) {
    const at = /^(?:jobs?|careers?|vacancies)\s+(?:at|with|@)\s+(.+)$/i.exec(part);
    if (at) {
      company = company || at[1];
      continue;
    }
    // Board/site tails ("Indeed.com", "Careers") name the site, not the job.
    if (BOARD_NOISE.test(part) || DOMAIN_LIKE.test(part)) continue;
    kept.push(part);
  }
  let title = kept[0] || null;
  const titleAt = title ? /^(.*\S)\s+(?:at|@)\s+(\S.*)$/i.exec(title) : null;
  if (titleAt) {
    title = titleAt[1];
    company = company || titleAt[2];
  }
  if (!company && kept.length > 1) company = kept[kept.length - 1];
  return { title: clean(title), company: clean(company) };
}

function descriptionFromDom(): string | null {
  const selectors = [
    '[itemprop="description"]',
    '[class*="job-description" i]',
    '[class*="jobdescription" i]',
    '[id*="job-description" i]',
    '[class*="description" i]',
    '[id*="description" i]',
    "main",
    "article",
  ];
  for (const selector of selectors) {
    for (const el of query(selector)) {
      const text = block(el.innerText);
      if (text && text.length >= 200) return text;
    }
  }
  return block(document.body?.innerText || null);
}

function applyUrlFromDom(): string | null {
  const links = query("a[href]") as HTMLAnchorElement[];
  const link = links.find((a) => /^\s*apply\b/i.test(a.innerText || a.textContent || ""));
  return absolute(link?.getAttribute("href"));
}

function postedFromDom(): string | null {
  const time = document.querySelector<HTMLTimeElement>("time[datetime]");
  const stamp = clean(time?.getAttribute("datetime"));
  if (stamp) return stamp;
  return (
    firstMatch(['[class*="posted" i]', '[class*="date-posted" i]']) ||
    labelledValue(/posted|date posted/i)
  );
}

function fromDom(): Draft {
  const fallback = fromDocumentTitle();
  const heading = shortText(document.querySelector("h1"), MAX_SHORT);
  return {
    title: heading || fallback.title,
    company:
      firstMatch([
        '[itemprop="hiringOrganization"]',
        '[data-testid*="company" i]',
        '[class*="company" i]',
        '[id*="company" i]',
        '[class*="employer" i]',
        '[id*="employer" i]',
        '[class*="organisation" i]',
        '[class*="organization" i]',
      ]) ||
      labelledValue(/company|employer|organisation|organization/i) ||
      fallback.company,
    location:
      firstMatch([
        '[itemprop="jobLocation"]',
        '[data-testid*="location" i]',
        '[class*="location" i]',
        '[id*="location" i]',
        '[class*="workplace" i]',
      ]) || labelledValue(/location|workplace|based in/i),
    description: descriptionFromDom(),
    salary_raw:
      firstMatch([
        '[itemprop="baseSalary"]',
        '[class*="salary" i]',
        '[id*="salary" i]',
        '[class*="compensation" i]',
        '[class*="pay-range" i]',
      ]) || labelledValue(/salary|compensation|pay range/i),
    apply_url: applyUrlFromDom(),
    posted_at_text: postedFromDom(),
  };
}

const HOST_NOISE = /^(?:www|careers?|jobs?|boards?|apply|my|hire|talent)$/i;
// Second-level pieces of multi-part public suffixes ("bigco.co.uk").
const HOST_SUFFIX = /^(?:co|com|net|org|ac|gov|edu)$/i;

/** Last resort for the company: the site the user is reading it on. */
function companyFromHost(): string {
  const labels = location.hostname.split(".").filter((label) => !HOST_NOISE.test(label));
  if (labels.length > 1) labels.pop(); // the TLD
  if (labels.length > 1 && HOST_SUFFIX.test(labels[labels.length - 1])) labels.pop();
  const name = labels[labels.length - 1] || location.hostname;
  return name ? name.charAt(0).toUpperCase() + name.slice(1) : "Unknown";
}

export function extractJob(): CapturedJob {
  const jsonld = fromJsonLd();
  const meta = fromMeta();
  const dom = fromDom();
  const layers = [jsonld, meta, dom].filter((layer): layer is Draft => layer !== null);
  const pick = (key: keyof Draft): string | null => {
    for (const layer of layers) {
      if (layer[key]) return layer[key];
    }
    return null;
  };

  const confidence: CaptureConfidence = jsonld
    ? "high"
    : meta.title || meta.description
      ? "medium"
      : "low";

  return {
    url: location.href.slice(0, MAX_URL),
    title: pick("title") || clean(document.title) || "Job posting",
    company: pick("company") || companyFromHost(),
    location: pick("location"),
    description: pick("description"),
    salary_raw: pick("salary_raw"),
    apply_url: pick("apply_url") || location.href.slice(0, MAX_URL),
    posted_at_text: pick("posted_at_text"),
    confidence,
  };
}
