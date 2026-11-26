"""Button that forces a full refresh of the portal data."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HygngConfigEntry
from .coordinator import CoordinatorEntityBase, HygngCoordinator

REFRESH_DESCRIPTION = ButtonEntityDescription(
    key="refresh",
    name="刷新账单",
    icon="mdi:refresh",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HygngConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the refresh button."""
    async_add_entities([HygngRefreshButton(entry.runtime_data.coordinator)])


class HygngRefreshButton(CoordinatorEntityBase, ButtonEntity):
    """Re-read every page, including the itemised ones."""

    entity_description = REFRESH_DESCRIPTION
    _attr_has_entity_name = True

    def __init__(self, coordinator: HygngCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.customer_id}_refresh"

    async def async_press(self) -> None:
        """Trigger a full refresh."""
        self.coordinator.request_full_refresh()
        await self.coordinator.async_refresh()
