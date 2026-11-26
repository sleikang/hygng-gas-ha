"""Binary sensor for the 惠州光能燃气 integration (outstanding balance)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HygngConfigEntry
from .coordinator import CoordinatorEntityBase, HygngCoordinator

ARREARS_DESCRIPTION = BinarySensorEntityDescription(
    key="arrears",
    name="欠费",
    icon="mdi:alert-circle-outline",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HygngConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the outstanding-balance sensor."""
    async_add_entities([HygngArrearsSensor(entry.runtime_data.coordinator)])


class HygngArrearsSensor(CoordinatorEntityBase, BinarySensorEntity):
    """On when the newest bill is not marked as settled."""

    entity_description = ARREARS_DESCRIPTION
    _attr_has_entity_name = True

    def __init__(self, coordinator: HygngCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.customer_id}_arrears"

    @property
    def is_on(self) -> bool | None:
        """Whether money is still owed."""
        if self.coordinator.data is None or self.coordinator.data.latest is None:
            return None
        return self.coordinator.data.unpaid

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        """Show which bill is open."""
        data = self.coordinator.data
        if data is None or data.latest is None:
            return None
        latest = data.latest
        return {
            "fee_month": latest.fee_month,
            "status": latest.status,
            "amount": latest.amount,
            "sum_amount": latest.num("sum_amount"),
        }
