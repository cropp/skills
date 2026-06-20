from .rsi_mean_reversion import RSIMeanReversionStrategy

STRATEGY_REGISTRY = {
    "rsi_mean_reversion": RSIMeanReversionStrategy,
}

def get_strategy(name: str, params: dict):
    cls = STRATEGY_REGISTRY.get(name)
    if not cls:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(STRATEGY_REGISTRY.keys())}")
    return cls(params)
