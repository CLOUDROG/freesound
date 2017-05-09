# -*- coding: utf-8 -*-
# Generated by Django 1.9.5 on 2016-10-18 18:09
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sounds', '0006_auto_20161005_1533'),
    ]

    operations = [
        migrations.AddField(
            model_name='sound',
            name='is_explicit',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterUniqueTogether(
            name='pack',
            unique_together=set([('user', 'name', 'is_deleted')]),
        ),
    ]
