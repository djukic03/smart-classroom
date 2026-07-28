import enum


class MetricEnum(str, enum.Enum):
    CO2 = "CO2"
    TEMPERATURE = "TEMPERATURE"
    HUMIDITY = "HUMIDITY"
    ILLUMINANCE = "ILLUMINANCE"
    SOUND = "SOUND"
    OCCUPANCY = "OCCUPANCY"
