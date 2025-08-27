from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    if dictionary and key in dictionary:
        return dictionary.get(key)
    return None

@register.filter
def get_item1(dictionary, key):
    """Safely get dictionary item by key in template"""
    return dictionary.get(key, 0)


@register.filter
def get_dict_value(dictionary, key):
    """
    Safely fetches value from a dictionary using a dynamic key in Django templates.
    Usage: {{ my_dict|get_dict_value:key_var }}
    """
    try:
        if isinstance(dictionary, dict):
            return dictionary.get(key, "")
    except Exception:
        pass
    return ""