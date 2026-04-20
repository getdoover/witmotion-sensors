from pydoover.tags import Tag, Tags


class WitmotionSensorTags(Tags):
    link_state = Tag("string", default="disconnected")
    last_comms_ok = Tag("boolean", default=False)
    comms_error_count = Tag("integer", default=0)

    accel_x = Tag("number", default=0)
    accel_y = Tag("number", default=0)
    accel_z = Tag("number", default=0)

    velocity_x = Tag("number", default=0)
    velocity_y = Tag("number", default=0)
    velocity_z = Tag("number", default=0)

    displacement_x = Tag("number", default=0)
    displacement_y = Tag("number", default=0)
    displacement_z = Tag("number", default=0)

    frequency_x = Tag("number", default=0)
    frequency_y = Tag("number", default=0)
    frequency_z = Tag("number", default=0)

    temperature = Tag("number", default=0)

    velocity_peak = Tag("number", default=0)
    displacement_peak = Tag("number", default=0)
    frequency_dominant = Tag("number", default=0)

    cmd_set_slave_id = Tag("integer", default=None)
    cmd_set_sample_rate = Tag("integer", default=None)
    cmd_set_baud_code = Tag("integer", default=None)
    cmd_factory_reset = Tag("boolean", default=None)
    cmd_save_config = Tag("boolean", default=None)
