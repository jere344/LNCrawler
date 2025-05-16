from django import forms

class MetaJsonImportForm(forms.Form):
    meta_json_path = forms.CharField(
        label='Path to meta.json file',
        max_length=500,
        help_text='Enter the full path to a meta.json file (e.g., C:\\Users\\Jeremy\\novels\\novel_name\\meta.json)'
    )

class MassImportForm(forms.Form):
    IMPORT_ACTIONS = [
        ('import_only', 'Import Only (No File Operations)'),
        ('copy', 'Copy to Library Path and Import'),
        ('move', 'Move to Library Path and Import')
    ]
    
    root_directory = forms.CharField(
        label='Root Directory Path',
        max_length=500,
        help_text='Enter the full path to a directory to recursively search for meta.json files (e.g., C:\\Users\\Jeremy\\novels)'
    )
    
    import_action = forms.ChoiceField(
        label='Import Action',
        choices=IMPORT_ACTIONS,
        initial='import_only',
        help_text='Select whether to just import, or copy/move files to library path before importing'
    )
