from queryfi.courses import Subject, SubjectId


class MemorySubjects:
    def __init__(self):
        self.subjects = (Subject(SubjectId("math"), "Mathematics"),)
        self.error = None

    def list_subjects(self):
        if self.error:
            raise self.error
        return self.subjects


class MemoryBindings:
    def __init__(self):
        self.bindings = {}

    def for_guild(self, guild_id):
        return {channel.channel_id: subject for channel, subject in self.bindings.items()
                if channel.guild_id == guild_id}

    def bind(self, channel, subject_id):
        self.bindings[channel] = subject_id
