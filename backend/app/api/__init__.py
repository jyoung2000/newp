from fastapi import APIRouter

from app.api import (
    analytics,
    applications,
    auth,
    custom_fields,
    devices,
    extension,
    files,
    interventions,
    listings,
    meta,
    profile,
    roles,
    runs,
    saved_answers,
    search,
    transfer,
    users,
)
from app.api import (
    settings as settings_api,
)
from app.api import ws as ws_module

api_router = APIRouter()
api_router.include_router(meta.router, tags=["meta"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(profile.router, prefix="/profile", tags=["profile"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(custom_fields.router, prefix="/custom-fields", tags=["custom-fields"])
api_router.include_router(saved_answers.router, prefix="/saved-answers", tags=["saved-answers"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(listings.router, prefix="/listings", tags=["listings"])
api_router.include_router(applications.router, prefix="/applications", tags=["applications"])
api_router.include_router(runs.router, prefix="/runs", tags=["runs"])
api_router.include_router(
    interventions.router, prefix="/interventions", tags=["interventions"]
)
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
api_router.include_router(extension.router, prefix="/ext", tags=["extension"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(transfer.router, prefix="/transfer", tags=["transfer"])
api_router.include_router(settings_api.router, prefix="/settings", tags=["settings"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(roles.router, prefix="/roles", tags=["roles"])

ws_router = ws_module.router
