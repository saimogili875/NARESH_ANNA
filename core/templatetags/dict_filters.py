from django import template
register = template.Library()

@register.filter
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None

@register.filter
def zip_lists(a, b):
    return zip(a, b)

# Register as 'zip' in template
register.filter('zip', zip_lists)

@register.filter
def attr(obj, field_name):
    """{{ obj|attr:'field_name' }} — safe getattr"""
    val = getattr(obj, field_name, None)
    return '' if val is None else val
