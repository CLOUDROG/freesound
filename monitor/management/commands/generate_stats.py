#
# Freesound is (c) MUSIC TECHNOLOGY GROUP, UNIVERSITAT POMPEU FABRA
#
# Freesound is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# Freesound is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Authors:
#     See AUTHORS file.
#

from django.core.management.base import NoArgsCommand
from django.core.cache import cache
from django.contrib.auth.models import User
from django.db import connection
from django.db.models import Count, Sum
from tags.models import Tag, TaggedItem
import datetime
import sounds.views
import donations.views
import forum.models
import ratings.models
import comments.models
import logging

logger = logging.getLogger("web")


class Command(NoArgsCommand):
    help = "Compute stats to display on monitor section."

    def handle(self, **options):
        logger.info("Command started")

        time_span = datetime.datetime.now()-datetime.timedelta(weeks=2)

        # Compute stats relatad with sounds:

        new_sounds_mod = sounds.models.Sound.objects\
                .filter(created__gt=time_span, moderation_date__isnull=False)\
                .extra(select={'day': 'date(moderation_date)'}).values('day')\
                .order_by().annotate(Count('id'))

        new_sounds = sounds.models.Sound.objects\
                .filter(created__gt=time_span, processing_date__isnull=False)\
                .extra(select={'day': 'date(processing_date)'}).values('day')\
                .order_by().annotate(Count('id'))

        sounds_stats = {
            "new_sounds_mod": list(new_sounds_mod),
            "new_sounds": list(new_sounds)
        }
        cache.set("sounds_stats", sounds_stats, 60 * 60 * 24)

        # Compute stats related with downloads:
        new_downloads_sound = sounds.models.Download.objects\
            .filter(created__gt=time_span, pack=None)\
            .extra({'day': 'date(created)'}).values('day').order_by()\
            .annotate(Count('id'))

        new_downloads_pack = sounds.models.Download.objects\
            .filter(created__gt=time_span, sound=None)\
            .extra({'day': 'date("sounds_download".created)'}).values('day').order_by()\
            .annotate(id__count=Sum('pack__num_sounds'))

        downloads_stats = {
            'new_downloads_sound': list(new_downloads_sound),
            'new_downloads_pack': list(new_downloads_pack),
        }

        cache.set("downloads_stats", downloads_stats, 60 * 60 * 24)

        # Compute stats relatad with users:
        new_users = User.objects.filter(date_joined__gt=time_span)\
            .extra(select={'day': 'date(date_joined)'})\
            .values('day', 'is_active').order_by().annotate(Count('id'))

        cache.set("users_stats", {"new_users": list(new_users)}, 60 * 60 * 24)


        time_span = datetime.datetime.now()-datetime.timedelta(days=365)

        active_users = {
            'sounds': {'obj': sounds.models.Sound.objects, 'attr': 'user'},
            'comments': {'obj': comments.models.Comment.objects, 'attr': 'user'},
            'posts': {'obj': forum.models.Post.objects, 'attr': 'author'},
            'downloads': {'obj': sounds.models.Download.objects, 'attr': 'user'},
            'rate': {'obj': ratings.models.Rating.objects, 'attr': 'user'},
        }
        for i in active_users.keys():
            qq = active_users[i]['obj'].filter(created__gt=time_span)\
                .extra({'week': "to_char(created, 'WW-IYYY')"})\
                .values('week').order_by().annotate(Count(active_users[i]['attr']))

            converted_weeks = [{
                'week': str(datetime.datetime.strptime(d['week']+ '-0', "%W-%Y-%w").date()),
                'amount__sum': d[active_users[i]['attr']+'__count']
            } for d in qq]

            active_users[i] = converted_weeks
        cache.set("active_users_stats", active_users, 60 * 60 * 24)

        # Compute stats related with donations:
        query_donations = donations.models.Donation.objects\
            .filter(created__gt=time_span)\
            .extra({'week': "to_char(created, 'WW-IYYY')"})\
            .values('week').order_by()\
            .annotate(Sum('amount'))

        new_donations = [{
            'week': str(datetime.datetime.strptime(d['week']+ '-0', "%W-%Y-%w").date()),
            'amount__sum': d['amount__sum']
        } for d in query_donations]

        cache.set('donations_stats', {'new_donations': new_donations}, 60*60*24)

        # Compute stats related with Tags:
        time_span = datetime.datetime.now()-datetime.timedelta(weeks=2)

        top_tags = TaggedItem.objects.filter(created__gt=time_span)\
            .values('tag_id').distinct().annotate(num=Count('tag_id'))\
            .order_by('-num')[:30]
        top_tags = [t['tag_id'] for t in  top_tags]
        tags_stats = TaggedItem.objects\
            .filter(tag_id__in=top_tags, created__gt=time_span)\
            .extra(select={'day': 'date(created)'})\
            .values('day', 'tag__name').order_by().annotate(Count('tag_id'))

        tags = {i['tag__name']: [] for i in tags_stats}
        for i in tags_stats:
            tags[i['tag__name']].append({
                'count': i['tag_id__count'],
                'day': i['day']
            })

        # Most used tags for tags cloud
        all_tags = TaggedItem.objects.values('tag_id')\
                .annotate(num=Count('tag_id'))\
                .values('num', 'tag__name').order_by('-num')[:300]

        with connection.cursor() as cursor:
            cursor.execute(\
                    """SELECT count(*) as num_c, t.name, ti.tag_id as id FROM
                    tags_taggeditem ti, tags_tag t, sounds_download d
                    WHERE d.sound_id = ti.object_id AND t.id = ti.tag_id
                    AND d.created > current_date - interval '14 days'
                    GROUP BY ti.tag_id, t.name ORDER BY num_c limit 300""")

            downloads_tags = cursor.fetchall()

        tags_stats = {
            "tags_stats": tags,
            "all_tags": list(all_tags),
            "downloads_tags": list(downloads_tags)
        }

        cache.set('tags_stats', tags_stats, 60*60*24)

        # Compute stats for Totals table:

        users = User.objects.filter(is_active=True)
        users_num = users.count()
        users_with_sounds = users.filter(profile__num_sounds__gt=0).count()
        num_donations = donations.models.Donation.objects\
            .aggregate(Sum('amount'))['amount__sum']

        num_sounds = sounds.models.Sound.objects.filter(processing_state="OK",
            moderation_state="OK").count()
        packs = sounds.models.Pack.objects.all().count()

        downloads = sounds.models.Download.objects.all().count()
        num_comments = comments.models.Comment.objects.all().count()
        num_ratings = ratings.models.Rating.objects.all().count()

        tags = Tag.objects.all().count()
        tags_used = TaggedItem.objects.all().count()

        posts = forum.models.Post.objects.all().count()
        threads = forum.models.Thread.objects.all().count()

        totals_stats = {
            "total_users": users_num,
            "users_with_sounds": users_with_sounds,
            "total_donations": num_donations,
            "sounds": num_sounds,
            "packs": packs,
            "downloads": downloads,
            "comments": num_comments,
            "ratings": num_ratings,
            "tags": tags,
            "tags_used": tags_used,
            "posts": posts,
            "threads": threads,
        }

        cache.set('totals_stats', totals_stats, 60*60*24)
