import re
import os

views_path = 'marks/views.py'
with open(views_path, 'r') as f:
    views_content = f.read()

# I will replace the top part of views.py up to `exam_list` definition.
# Actually it is easier to write the full views.py.
