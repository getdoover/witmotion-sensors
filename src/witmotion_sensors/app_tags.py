from pydoover.tags import Tag, Tags


class WitmotionSensorTags(Tags):
    link_state = Tag("boolean", default=False)
    last_comms_ok = Tag("boolean", default=False)
    comms_error_count = Tag("integer", default=0)

    accel_x = Tag("number", default=None, live=True)
    accel_y = Tag("number", default=None, live=True)
    accel_z = Tag("number", default=None, live=True)

    velocity_x = Tag("number", default=None, live=True)
    velocity_y = Tag("number", default=None, live=True)
    velocity_z = Tag("number", default=None, live=True)

    displacement_x = Tag("number", default=None, live=True)
    displacement_y = Tag("number", default=None, live=True)
    displacement_z = Tag("number", default=None, live=True)

    frequency_x = Tag("number", default=None, live=True)
    frequency_y = Tag("number", default=None, live=True)
    frequency_z = Tag("number", default=None, live=True)

    temperature = Tag("number", default=None, live=True)

    velocity_peak = Tag("number", default=None, live=True)
    displacement_peak = Tag("number", default=None, live=True)
    frequency_dominant = Tag("number", default=None, live=True)

    cmd_set_slave_id = Tag("integer", default=None)
    cmd_set_sample_rate = Tag("integer", default=None)
    cmd_set_baud_code = Tag("integer", default=None)
    cmd_factory_reset = Tag("boolean", default=None)
    cmd_save_config = Tag("boolean", default=None)
