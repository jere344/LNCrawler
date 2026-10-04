from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth_app', '0008_customuser_banner_customuser_bio_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='passwordresettoken',
            name='token',
            field=models.CharField(max_length=64, unique=True),
        ),
    ]
