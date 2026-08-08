# plugin.video.youtube local patches

Re-apply after any YouTube addon update.

1. `helper/utils.py`, stats loop (~line 906): skip `commentCount` so the
   Couch YouTube page's stats line reads "views | likes" only (Donnie,
   8 Aug 2026: "i don't want to see comment count").

   ```python
   for stat, value in yt_item['statistics'].items():
       if not value:
           continue
       # Couch: comment counts add noise to the video cards - skip.
       if stat == 'commentCount':
           continue
   ```

2. `helper/utils.py`, video plot assembly (~line 1002): the plot is
   rendered on the Couch YouTube cards, so it's cut to channel + stats
   (+ live start time) - description, '--------' and youtu.be URL removed
   (Donnie, 8 Aug 2026: "can we not have descriptions in it please").

3. Not a code patch, but related: stat label colours are set to the
   Stagelight palette in the ADDON'S USER SETTINGS (survives updates):
   viewCount ffb4bcc8, likeCount ff8a93a0, commentCount ff8a93a0
   (`~/.kodi/userdata/addon_data/plugin.video.youtube/settings.xml`).
