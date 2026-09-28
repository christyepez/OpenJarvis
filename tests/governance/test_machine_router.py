from openjarvis.governance import (
    MachineDescriptor,
    MachineRequirement,
    MachineRouter,
)


def test_machine_router_prefers_trabajo() -> None:
    router = MachineRouter()
    machines = [
        MachineDescriptor("MarketingIndo", online=True, docker_available=True),
        MachineDescriptor("trabajo", online=True, docker_available=True),
    ]

    selected = router.select(machines, MachineRequirement(require_docker=True))

    assert selected is not None
    assert selected.name == "trabajo"
def test_machine_router_falls_back_to_marketingindo() -> None:
    router = MachineRouter()
    machines = [
        MachineDescriptor("trabajo", online=False, docker_available=True),
        MachineDescriptor("MarketingIndo", online=True, docker_available=True),
    ]

    selected = router.select(machines, MachineRequirement(require_docker=True))

    assert selected is not None
    assert selected.name == "MarketingIndo"


def test_machine_router_respects_gpu_requirement() -> None:
    router = MachineRouter()
    machines = [
        MachineDescriptor("trabajo", online=True, gpu_available=False),
        MachineDescriptor("MarketingIndo", online=True, gpu_available=True),
    ]

    selected = router.select(machines, MachineRequirement(require_gpu=True))

    assert selected is not None
    assert selected.name == "MarketingIndo"
