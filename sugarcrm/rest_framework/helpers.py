class Field:
    """
    Class needs to support DRF filtering system
    """
    def __init__(self, name):
        self.name = name
        self.verbose_name = self.name.replace('_', ' ')


class Meta:
    """
    Class need to support DRF views
    """
    def __init__(self, object_name):
        self.object_name = object_name

    def get_field(self, name):
        """
        method needs to support DRF filtering system
        """
        return Field(name)
