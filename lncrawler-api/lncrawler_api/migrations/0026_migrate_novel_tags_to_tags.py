# Generated by Django 5.2.1 on 2025-05-26 14:22

from django.db import migrations


from django.db import migrations
import json

def migrate_tags(apps, schema_editor):
    """
    Migrates data from novel_tags TextField to tags ManyToMany relationship
    """
    NovelFromSource = apps.get_model('lncrawler_api', 'NovelFromSource')
    Tag = apps.get_model('lncrawler_api', 'Tag')
    
    # Loop through all novels with novel_tags data
    for novel_source in NovelFromSource.objects.exclude(novel_tags__isnull=True).exclude(novel_tags=''):
        try:
            # novel_tags could be a JSON string or already parsed
            if isinstance(novel_source.novel_tags, str):
                try:
                    tags_list = json.loads(novel_source.novel_tags)
                except json.JSONDecodeError:
                    # ['Fantasy', 'New Life'] it's a simple list string
                    tags_list = [tag.replace("'", "").replace('"', '').strip() for tag in novel_source.novel_tags.strip("[]").split(',')]
            else:
                tags_list = novel_source.novel_tags
            
            # Create and associate tags
            for tag_name in tags_list:
                if tag_name and tag_name.strip():
                    tag, _ = Tag.objects.get_or_create(name=tag_name.strip())
                    novel_source.tags.add(tag)
            
            # Clear the old field after migration
            novel_source.novel_tags = None
            novel_source.save()
            
        except Exception as e:
            print(f"Error migrating tags for {novel_source.id}: {e}")

def reverse_migrate(apps, schema_editor):
    """
    Reverses the migration (if needed)
    """
    NovelFromSource = apps.get_model('lncrawler_api', 'NovelFromSource')
    
    for novel_source in NovelFromSource.objects.all():
        tags_list = [tag.name for tag in novel_source.tags.all()]
        if tags_list:
            novel_source.novel_tags = json.dumps(tags_list)
            novel_source.save()


class Migration(migrations.Migration):

    dependencies = [
        ("lncrawler_api", "0025_novelfromsource_overview_picture_path"),
    ]

    operations = [
        migrations.RunPython(migrate_tags, reverse_migrate),
    ]
