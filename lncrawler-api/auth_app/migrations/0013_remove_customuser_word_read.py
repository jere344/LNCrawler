from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('auth_app', '0012_alter_customuser_show_r18_default'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='customuser',
            name='word_read',
        ),
    ]
