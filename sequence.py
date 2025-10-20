class Sequence:
    def __init__(self, name, priority=1, loop=False):
        self.name = name
        self.priority = priority
        # Each step: (scene_dict, duration, transition_time)
        self.steps = []
        self.loop = loop  # ✅ loop flag

    def add_step(self, scene_name, duration, transition):
        """Add a scene reference to this sequence."""
        self.steps.append({
            "scene_name": scene_name,
            "duration": duration,
            "transition": transition
        })
