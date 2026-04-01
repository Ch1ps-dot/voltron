####  TARGET INFORMATIOn
SUT Name: forked-daapd
daap stands for "Digital Audio Access Protocol", which is a protocol used for sharing and streaming music over a network. forked-daapd is an open-source implementation of the DAAP protocol, allowing users to share their music libraries and stream music to compatible clients. It uses HTTP as the underlying transport protocol and provides a web-based interface for managing the music library and streaming settings.

#### URI of some media files
directory=/tmp/MP3/David Hilowitz/Gradual Sunrise
directory=/tmp/MP3/Mild_Wild/a_Line_Spacing_b_Say_Goodnight
directory=/tmp/MP3/Mild_Wild/Particular_PacePrimary_Colors
directory=/tmp/MP3/Scott Holmes/Storybook
directory=/tmp/MP3/Scott Holmes/Upbeat Party

#### API INTERFACE

**Player**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/player | Get player status |
| PUT | /api/player/play, /api/player/pause, /api/player/stop, /api/player/toggle | Start, pause or stop playback |
| PUT | /api/player/next, /api/player/previous | Skip forward or backward |
| PUT | /api/player/shuffle | Set shuffle mode |
| PUT | /api/player/consume | Set consume mode |
| PUT | /api/player/repeat | Set repeat mode |
| PUT | /api/player/volume | Set master volume or volume for a specific output |
| PUT | /api/player/seek | Seek to a position in the currently playing track |

**Outputs**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/outputs | Get a list of available outputs |
| PUT | /api/outputs/set | Set enabled outputs |
| GET | /api/outputs/{id} | Get an output |
| PUT | /api/outputs/{id} | Change an output setting |
| PUT | /api/outputs/{id}/toggle | Enable or disable an output, depending on the current state |


**Queue**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/queue | Get a list of queue items |
| PUT | /api/queue/clear | Remove all items from the queue |
| POST | /api/queue/items/add | Add items to the queue |
| PUT | /api/queue/items/{id}\|now_playing | Updating a queue item in the queue |
| DELETE | /api/queue/items/{id} | Remove a queue item from the queue |

**Library**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/library | Get library information |
| GET | /api/library/playlists | Get a list of playlists |
| GET | /api/library/playlists/{id} | Get a playlist |
| PUT | /api/library/playlists/{id} | Update a playlist attribute |
| DELETE | /api/library/playlists/{id} | Delete a playlist |
| GET | /api/library/playlists/{id}/tracks | Get list of tracks for a playlist |
| PUT | /api/library/playlists/{id}/tracks | Update play count of tracks for a playlist |
| GET | /api/library/playlists/{id}/playlists | Get list of playlists for a playlist folder |
| GET | /api/library/artists | Get a list of artists |
| GET | /api/library/artists/{id} | Get an artist |
| GET | /api/library/artists/{id}/albums | Get list of albums for an artist |
| GET | /api/library/albums | Get a list of albums |
| GET | /api/library/albums/{id} | Get an album |
| GET | /api/library/albums/{id}/tracks | Get list of tracks for an album |
| GET | /api/library/tracks/{id} | Get a track |
| GET | /api/library/tracks/{id}/playlists | Get list of playlists for a track |
| PUT | /api/library/tracks | Update multiple track properties |
| PUT | /api/library/tracks/{id} | Update single track properties |
| GET | /api/library/genres | Get list of genres |
| GET | /api/library/count | Get count of tracks, artists and albums |
| GET | /api/library/files | Get list of directories in the local library |
| POST | /api/library/add | Add an item to the library |
| PUT | /api/update | Trigger a library rescan |
| PUT | /api/rescan | Trigger a library metadata rescan |
| PUT | /api/library/backup | Request library backup db |