"""Sanity checks that every feature router can be imported and exposes routes."""

import importlib

import pytest

from app.main import _include_routers, create_application

ROUTER_MODULES = [
    "app.routers.admin_dashboard",
    "app.routers.amenhotep",
    "app.routers.auth",
    "app.routers.banned_words",
    "app.routers.block",
    "app.routers.business",
    "app.routers.call",
    "app.routers.category_management",
    "app.routers.comment",
    "app.routers.community",
    "app.routers.follow",
    "app.routers.insights",
    "app.routers.hashtag",
    "app.routers.message",
    "app.routers.moderation",
    "app.routers.oauth",
    "app.routers.p2fa",
    "app.routers.post",
    "app.routers.reaction",
    "app.routers.screen_share",
    "app.routers.search",
    "app.routers.session",
    "app.routers.social_auth",
    "app.routers.statistics",
    "app.routers.sticker",
    "app.routers.support",
    "app.routers.user",
    "app.routers.vote",
]

@pytest.mark.parametrize("module_name", ROUTER_MODULES)
def test_router_modules_export_routes(module_name):
    module = importlib.import_module(module_name)
    router = getattr(module, "router", None)
    assert router is not None, f"{module_name} does not expose a router"
    assert router.routes, f"{module_name} router has no registered routes"
    for route in router.routes:
        assert route.path.startswith("/"), "All routes should start with a slash"
        if router.prefix:
            assert route.path.startswith(router.prefix), "Route path should honour router prefix"


def test_include_routers_registers_all_router_paths():
    app = create_application()
    _include_routers(app)
    registered_paths = {route.path for route in app.router.routes}
    for module_name in ROUTER_MODULES:
        router_paths = {
            route.path
            for route in getattr(importlib.import_module(module_name), "router").routes
        }
        assert registered_paths & router_paths, f"{module_name} routes not registered"
