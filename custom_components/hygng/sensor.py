"""Sensors for the 惠州光能燃气 integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import HygngConfigEntry
from .coordinator import CoordinatorEntityBase, HygngCoordinator, HygngData


def _as_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _tier_label(data: HygngData) -> str | None:
    tier = data.current_tier
    if tier is None:
        return None
    return {1: "第一档", 2: "第二档", 3: "第三档"}.get(tier, f"第{tier}档")


@dataclass(frozen=True, kw_only=True)
class HygngSensorEntityDescription(SensorEntityDescription):
    """A sensor description bound to a value extractor."""

    value_fn: Callable[[HygngData], StateType] = lambda data: None
    attr_fn: Callable[[HygngData], dict[str, Any]] | None = None


SENSORS: tuple[HygngSensorEntityDescription, ...] = (
    HygngSensorEntityDescription(
        key="current_amount",
        name="本月气费",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="CNY",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        icon="mdi:cash-multiple",
        value_fn=lambda data: data.latest.amount if data.latest else None,
        attr_fn=lambda data: {
            "fee_month": data.latest.fee_month,
            "period_start": data.latest.period_start,
            "period_end": data.latest.period_end,
            "status": data.latest.status,
            "bill_title": data.latest.get("bill_title"),
        }
        if data.latest
        else {},
    ),
    HygngSensorEntityDescription(
        key="current_usage",
        name="本月用气量",
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:fire",
        value_fn=lambda data: data.latest.usage if data.latest else None,
    ),
    HygngSensorEntityDescription(
        key="daily_average",
        name="日均用气量",
        native_unit_of_measurement="m³/d",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:chart-line",
        value_fn=lambda data: data.latest.daily_average if data.latest else None,
        attr_fn=lambda data: {
            "chart": data.usage.get("chart", []) if data.usage else [],
        },
    ),
    HygngSensorEntityDescription(
        key="usage_days",
        name="用气天数",
        native_unit_of_measurement="天",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-range",
        value_fn=lambda data: data.latest.qty_day if data.latest else None,
    ),
    HygngSensorEntityDescription(
        key="unit_price",
        name="用气单价",
        native_unit_of_measurement="元/m³",
        suggested_display_precision=3,
        icon="mdi:tag-outline",
        value_fn=lambda data: data.latest.price if data.latest else None,
    ),
    HygngSensorEntityDescription(
        key="meter_reading",
        name="本次抄表度数",
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        icon="mdi:gauge",
        value_fn=lambda data: data.latest.meter_reading if data.latest else None,
        attr_fn=lambda data: {
            "read_date": data.latest.period_end,
            "read_type": data.latest.get("read_type"),
            "previous_reading": data.latest.previous_reading,
            "previous_read_date": data.latest.period_start,
        }
        if data.latest
        else {},
    ),
    HygngSensorEntityDescription(
        key="previous_reading",
        name="上次抄表度数",
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:gauge",
        value_fn=lambda data: data.latest.previous_reading if data.latest else None,
    ),
    HygngSensorEntityDescription(
        key="penalty",
        name="违约金",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="CNY",
        suggested_display_precision=2,
        icon="mdi:alert-circle-outline",
        value_fn=lambda data: (data.detail or {}).get("penalty")
        if data.detail
        else (data.latest.num("penalty_amount") if data.latest else None),
    ),
    HygngSensorEntityDescription(
        key="ladder_amount",
        name="超档气费",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="CNY",
        suggested_display_precision=2,
        icon="mdi:stairs",
        value_fn=lambda data: (data.detail or {}).get("ladder_amount")
        if data.detail
        else (data.latest.num("ladder_amount") if data.latest else None),
    ),
    HygngSensorEntityDescription(
        key="sum_amount",
        name="合计应缴气费",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="CNY",
        suggested_display_precision=2,
        icon="mdi:cash-check",
        value_fn=lambda data: (data.detail or {}).get("sum_amount")
        if data.detail
        else (data.latest.num("sum_amount") if data.latest else None),
    ),
    HygngSensorEntityDescription(
        key="unpaid_prev",
        name="前期未缴气费",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="CNY",
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        icon="mdi:cash-clock",
        value_fn=lambda data: (data.detail or {}).get("unpaid_prev"),
    ),
    HygngSensorEntityDescription(
        key="capacity_price",
        name="本月容量气价",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="CNY",
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        icon="mdi:cash-lock",
        value_fn=lambda data: (data.detail or {}).get("capacity_price"),
    ),
    HygngSensorEntityDescription(
        key="payment_status",
        name="缴费状态",
        icon="mdi:cash-check",
        value_fn=lambda data: data.latest.status if data.latest else None,
        attr_fn=lambda data: {
            "is_paid": data.latest.is_paid if data.latest else None,
        },
    ),
    HygngSensorEntityDescription(
        key="bill_period",
        name="计费周期",
        icon="mdi:calendar-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (
            f"{data.latest.period_start} 至 {data.latest.period_end}"
            if data.latest
            else None
        ),
    ),
    HygngSensorEntityDescription(
        key="read_type",
        name="本次抄表方式",
        icon="mdi:remote",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.latest.get("read_type") if data.latest else None,
    ),
    HygngSensorEntityDescription(
        key="read_date",
        name="本次抄表日期",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:calendar-check",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _as_date(data.latest.period_end) if data.latest else None,
    ),
    HygngSensorEntityDescription(
        key="year_usage",
        name="年度累计用气量",
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        icon="mdi:sigma",
        value_fn=lambda data: data.year_usage,
        attr_fn=lambda data: {
            "year": data.latest.fee_month[:4] if data.latest else None,
            "tiers": data.tiers,
        },
    ),
    HygngSensorEntityDescription(
        key="year_amount",
        name="年度累计气费",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="CNY",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        icon="mdi:cash-plus",
        value_fn=lambda data: data.year_amount,
    ),
    HygngSensorEntityDescription(
        key="current_tier",
        name="当前阶梯",
        icon="mdi:stairs",
        value_fn=_tier_label,
        attr_fn=lambda data: {
            "tier": data.current_tier,
            "year_usage": data.year_usage,
            "tiers": data.tiers,
        },
    ),
    HygngSensorEntityDescription(
        key="fee_month",
        name="最近账期",
        icon="mdi:calendar-month",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.latest.fee_month if data.latest else None,
        attr_fn=lambda data: {
            "updated_at": data.updated_at.isoformat() if data.updated_at else None,
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HygngConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors of one account."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        HygngSensor(coordinator, description) for description in SENSORS
    )


class HygngSensor(CoordinatorEntityBase, SensorEntity):
    """A single value read from the portal."""

    entity_description: HygngSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HygngCoordinator,
        description: HygngSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.customer_id}_{description.key}"

    @property
    def native_value(self) -> StateType:
        """Current value from the coordinator payload."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Extra details attached to the value."""
        if self.coordinator.data is None or self.entity_description.attr_fn is None:
            return None
        return self.entity_description.attr_fn(self.coordinator.data)
