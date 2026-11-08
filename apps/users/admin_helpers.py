"""
Helper callbacks for the Unfold Admin environment indicator.
"""


def environment_callback(request):
    """
    Shows a coloured environment badge in the top bar.
    Returns [label, colour] — colour maps to Unfold's theme tokens:
    "warning" = amber, "danger" = red, "info" = blue, "success" = green.
    """
    import os
    debug = os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')
    if debug:
        return ["Development", "warning"]
    return ["Production", "danger"]

