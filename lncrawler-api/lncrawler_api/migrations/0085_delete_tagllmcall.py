from django.db import migrations


class Migration(migrations.Migration):
    """Drop TagLLMCall: the tag judge's daily call budget is replaced by the
    request cap shared by every LLM workflow, counted from LLMUsage."""

    dependencies = [
        ("lncrawler_api", "0084_llmrequest"),
    ]

    operations = [
        migrations.DeleteModel(name="TagLLMCall"),
    ]
