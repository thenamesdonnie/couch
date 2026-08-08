# plugin.video.youtube local patches

Re-apply after any YouTube addon update.

1. `helper/utils.py`, stats loop (~line 906): skip `commentCount` AND
   `likeCount` so the stats line is views only (Donnie, 8 Aug 2026:
   "i don't want to see comment count" / "instead of like count can i
   get upload date").

   ```python
   for stat, value in yt_item['statistics'].items():
       if not value:
           continue
       # Couch: the cards show views + upload age; likes and
       # comment counts are noise - skip both.
       if stat in ('commentCount', 'likeCount'):
           continue
   ```

2. `helper/utils.py`, video plot assembly (~line 1002): the plot is
   rendered on the Couch YouTube cards, so it's cut to channel, then
   "views | <relative upload age>" ("2 days ago", from publishedAt via
   parse_to_dt) - likes, description, '--------' and youtu.be URL all
   removed (Donnie, 8 Aug 2026: "can we not have descriptions in it
   please" / "instead of like count can i get upload date or like x days
   ago"). The age computation is a small inline block in the
   show_details branch; grep for `stats_line`.

3. Not a code patch, but related: stat label colours are set to the
   Stagelight palette in the ADDON'S USER SETTINGS (survives updates):
   viewCount ffb4bcc8, likeCount ff8a93a0, commentCount ff8a93a0
   (`~/.kodi/userdata/addon_data/plugin.video.youtube/settings.xml`).
