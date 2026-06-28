from django.db import migrations

def seed_categories(apps, schema_editor):
    Category = apps.get_model('rewards', 'Category')
    categories = [
        ('TRAVEL', 'Travel rewards, flights, hotels'),
        ('FOOD', 'Dining, groceries, food delivery'),
        ('SHOPPING', 'Retail, online stores, shopping coupons'),
        ('CASHBACK', 'General cashback reward plans'),
        ('ENTERTAINMENT', 'Movies, music streaming, concerts'),
        ('BILLS', 'Utilities, phone recharge, subscription billing'),
        ('OTHERS', 'Miscellaneous rewards'),
    ]
    for name, desc in categories:
        Category.objects.get_or_create(
            name=name,
            defaults={'description': desc}
        )

def unseed_categories(apps, schema_editor):
    Category = apps.get_model('rewards', 'Category')
    Category.objects.filter(
        name__in=['TRAVEL', 'FOOD', 'SHOPPING', 'CASHBACK', 'ENTERTAINMENT', 'BILLS', 'OTHERS']
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('rewards', '0002_initial'),
    ]

    operations = [
        migrations.RunPython(seed_categories, unseed_categories),
    ]
