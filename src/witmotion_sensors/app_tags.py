from pydoover.tags import Delta, Tag, Tags


class WitmotionSensorTags(Tags):
    link_state = Tag("boolean", default=False)
    last_comms_ok = Tag("boolean", default=False)
    comms_error_count = Tag("integer", default=0)

    accel_x = Tag("number", default=None)
    accel_y = Tag("number", default=None)
    accel_z = Tag("number", default=None)

    velocity_x = Tag("number", default=None)
    velocity_y = Tag("number", default=None)
    velocity_z = Tag("number", default=None)

    displacement_x = Tag("number", default=None)
    displacement_y = Tag("number", default=None)
    displacement_z = Tag("number", default=None)

    frequency_x = Tag("number", default=None)
    frequency_y = Tag("number", default=None)
    frequency_z = Tag("number", default=None)

    temperature = Tag("number", default=None)

    velocity_peak = Tag("number", default=None, log_on=Delta(amount=10))
    displacement_peak = Tag("number", default=None, log_on=Delta(amount=20))
    frequency_dominant = Tag("number", default=None, log_on=Delta(amount=25))

    cmd_set_slave_id = Tag("integer", default=None)
    cmd_set_sample_rate = Tag("integer", default=None)
    cmd_set_baud_code = Tag("integer", default=None)
    cmd_factory_reset = Tag("boolean", default=None)
    cmd_save_config = Tag("boolean", default=None)
