"""Unified operator partition rules for stage/pipeline boundaries."""


def is_stage_boundary_operator(op_type: str) -> bool:
    """Remote stage-boundary rule (stage split)."""
    if not op_type:
        return False
    op = op_type.lower()
    return (
        'streaming' in op or
        op in {
            'exchangeoperator',
            'mergeoperator',
            'localexchangesinkoperator',
            'localexchangesourceoperator',
            'localmerge',
        }
    )


def is_pipeline_breaker_operator(op_type: str) -> bool:
    """Pipeline-breaker rule inside a stage (does NOT always imply stage split)."""
    if not op_type:
        return False
    op = op_type.lower()
    return op in {
        # 'localexchangesinkoperator',
        # 'localexchangesourceoperator',
        # 'localmerge',
        # 'lookupjoinoperator',
    }
