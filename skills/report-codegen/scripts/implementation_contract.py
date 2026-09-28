"""Separate business behavior requirements from a choice of generated framework."""


def require_bundled_layout(plan):
    """This scaffolder emits its bundled layout; it cannot preserve an arbitrary project."""
    contract = plan.get('implementation_contract')
    if contract is None:
        contract = plan.get('codegen_contract', {}).get('implementation_contract')
    if contract is None:
        return  # Legacy new-project plans retain compatibility.
    if not isinstance(contract, dict):
        raise ValueError('implementation_contract must be an object')
    mode = contract.get('mode')
    if mode in {'preserve_existing', 'native_python'}:
        raise ValueError('implementation_contract selects %s; adapt the reference/native project directly, not the bundled scaffold' % mode)
    if mode != 'bundled' or contract.get('confirmed') is not True or not contract.get('evidence'):
        raise ValueError('bundled layout requires an adopted implementation_contract and evidence')
    if contract.get('reference_supplied') is True and contract.get('migration_requested') is not True:
        raise ValueError('reference implementation must be preserved unless framework migration was requested')
