# Sri NRI Junior College Rules

The following rules must be strictly adhered to when working on the `srinri_sai` project:

## College Naming Convention
- **NEVER** use the hardcoded name "Sreenidhi College" or any other placeholder names in this project.
- **ALWAYS** use "**Sri NRI Junior College**" as the college name in all user-facing content (e.g., PDF titles, WhatsApp message templates, site headers, email content, and anywhere else the college's name is rendered).

## Dynamic Table Columns
- When rendering tables that have dynamically generated columns (such as the Fee Type tables where admin can add/remove types), do **not** hardcode the `colspan` for empty states (e.g., "No students found").
- Always compute the `colspan` dynamically based on the total number of columns present in that specific render. For example, use `colspan="{{ dynamic_list|length|add:'X' }}"` in Django templates, where `X` is the number of static columns.

## Database Migrations
- Whenever changing model `Meta` options (such as `verbose_name_plural` to control admin ordering) or any other model options, ensure that you run `python manage.py makemigrations <app>` immediately. These changes must be captured in the migration history to prevent deployment checks from failing.
