from app.knowledge.method_routing import MethodRouter


def test_trigger_router_selects_specific_method_and_honors_negative_boundaries():
    methods = [
        {
            "slug": "conversion-experiment",
            "applicability": ["conversion experiment"],
            "exclusions": ["quick social post"],
            "manifest": {
                "trigger_contract": {
                    "positive_signals": ["conversion experiment", "funnel hypothesis"],
                    "negative_signals": ["quick social post"],
                }
            },
        },
        {
            "slug": "social-calendar",
            "applicability": ["quick social post"],
            "exclusions": [],
            "manifest": {"trigger_contract": {"positive_signals": ["quick social post"], "negative_signals": []}},
        },
    ]

    router = MethodRouter()
    experiment = router.select(methods, "Need a conversion experiment for the checkout funnel hypothesis")
    social = router.select(methods, "Draft a quick social post announcing the sale")
    boundary = router.select(methods, "Use a conversion experiment but produce a quick social post")

    assert experiment.selected_slug == "conversion-experiment"
    assert social.selected_slug == "social-calendar"
    assert boundary.selected_slug == "social-calendar"


def test_trigger_router_reads_source_distillation_contract():
    methods = [
        {
            "slug": "intent-quality-product-inspection-loop",
            "manifest": {
                "distillation": {
                    "trigger_contract": {
                        "positive_signals": ["Mentions of AI code generation agents", "intent quality"],
                        "negative_signals": ["fully formal verification"],
                    }
                }
            },
        }
    ]

    router = MethodRouter()
    decision = router.select(methods, "Review AI-generated code for intent quality before release")
    excluded = router.select(methods, "AI-generated code with fully formal verification")

    assert decision.selected_slug == "intent-quality-product-inspection-loop"
    assert excluded.selected_slug is None
