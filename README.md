# WebODM's Plugin Directory

This is WebODM's plugin directory. Plugins listed here are also listed in WebODM. 

Browse the directory: https://plugins.webodm.org

## Contributing a plugin

To build a plugin, see https://docs.webodm.org/plugin-development-guide/. Once it's ready, to submit it to the directory you have two choices:

### In this repository

If you don't have a repository for your plugin, you can contribute it directly to this one. Add a folder in the `plugins/` containing at least a `manifest.json` and a `plugin.py`.

### From an external source

If you have your own repository, add an entry to [directory.json](https://github.com/WebODM/WebODM-Plugins/blob/main/directory.json) pointing to a `.zip` release of the plugin, including the SHA256 hash of the file:

```json
{
    "plugins": [
        {
            "url": "https://example.com/my-plugin.zip",
            "sha256": "..."
        }
    ]
}
```

You can compute the SHA256 hash with:

```bash
sha256sum my-plugin.zip
```

The zip must contain a single root folder with a `manifest.json` inside. Plugins whose download fails or whose checksum does not match are skipped.

## Requirements

To be listed in the index, your plugin must be released under an [OSI-approved](https://opensource.org/licenses) free and open source license.

## License

AGPLv3, see [LICENSE](LICENSE).
