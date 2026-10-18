# WebODM-Plugins-Guidance

A set of instructions for machines to assist in building WebODM Plugins.

Copy/paste this into your favorite agent:

```bash
We need to build a WebODM plugin: follow the instructions on https://github.com/WebODM/WebODM-Plugins/blob/main/guidance/index.md for all you need to know to get started.

The plugin should [enter what you want to build here]
```

## Purpose

The purpose of this repository is to provide instructions for machines to build [WebODM](https://github.com/WebODM/WebODM) plugins.

## References

Before starting, make sure to fetch and read the following documents:
 * https://docs.webodm.org/plugin-development-guide/
 * https://docs.webodm.org/installation/#docker
 * https://docs.webodm.org/architecture/
 * https://docs.webodm.org/contributing/

## Setting up the development environment

### Option A - WebODM Native

If you're on Windows, and WebODM is installed in a top level folder like C:\WebODM or D:\WebODM (or some other drive) AND your plugin does not need .JSX components that require webpack (which is not available) then you don't need a development environment. You can simply use the native installation. WebODM root is at C:\WebODM\resources\app\apps\WebODM and the log is in C:\WebODM\resources\app\logs\app.log

### Option B - Docker

If you're not on Windows, or WebODM native is not installed, or you need to use .JSX components which require webpack, you first need to install docker (ask user permission). Afterwards, you should be able to start a development environment by first downloading WebODM's source code (https://github.com/WebODM/WebODM/archive/refs/heads/master.zip or via git if git is installed) and running the docker compose command that is selected by running `./webodm.sh start --dev`. If a Bash compatible shell is not available, derive the equivalent command by reading `webodm.sh`. WebODM root is in /webodm inside the "webodm_webapp" container. The log is the output from the "webodm_webapp" container.

For both options, start from a copy of https://github.com/WebODM/WebODM/tree/master/coreplugins/hello-world and place it in the <WebODMRoot>/coreplugins. Rename `hello-world` to match the plugin name/id and update the manifest.json accordingly. Do not include a `disabled` file.

You might need to restart WebODM in order for the plugin to be picked up.

### Verification

Check this before continuing: the dev environment is setup OK if the startup log should include the line "INFO Registered [coreplugins.plugin-name.plugin]" and no errors related to the plugin.

## Ask Questions

It's likely the user's initial prompt lacks all the implementation details. Before implementing a single line of code, ask the user clarifying questions to better define the scope of the project and results.

## Styling and Rules

You should follow the following rules when building plugins for the user:
 * Never add tests, unless asked to
 * Your main guiding principle: keep it simple.
 * If you are designing UI components, NEVER include hard-coded colors. WebODM has theme colors that need to be respected. See https://github.com/WebODM/WebODM/blob/master/app/templates/app/theme.css
 * Prefer to write vanilla code from scratch, rather than include dependencies or libraries, unless this creates a lot of complexity.
 * Strive to write memory efficient code.
 * Strive to write fast, multi-threaded code whenever it makes sense.
 * Async functions should use `run_function_async` (https://github.com/WebODM/WebODM/blob/master/app/plugins/worker.py)
 * Eventually, the plugin ends up being located in <WebODMRoot>/app/media/plugins in production. Keep that in mind while you write imports.
 * Try to use available hooks and callbacks (https://github.com/WebODM/WebODM/tree/master/app/static/app/js/classes/plugins) on the Javascript side. If one is not available but is needed, instruct the user to discuss this with the WebODM maintainers on Discord (https://webodm.org/community)
 * If you need Python modules, try to use what's already available in https://github.com/WebODM/WebODM/blob/master/requirements.txt
 * As much as possible, try to keep the UI design of all elements similar in style and look with the rest of the WebODM interface
 * Keep in mind that UI elements need to be responsive (work on mobile as well as desktop)
 * Before distributing, always check and clean up the code for unused functions, modules, or other unused parts.
 * Before distributing, double check that the plugin's manifest information is correct.
 * The plugin should be marked as "experimental" unless the user requests otherwise.

## Iteration Cycle

After you've created the first code and verified that it loads, ask the user for feedback by guiding them on how to test the results. When the user is ready, get the plugin zipped and ready for sharing or submission to the WebODM Plugins directory.

## License of the Plugin

License should default to AGPLv3 by default, but point out that the user can change it to another OSI approved open source license if they wish.

## Submission to Plugins Directory

Guide the user with the process of submitting the final plugin (.zip), including it's SHA256 hash to https://github.com/WebODM/WebODM-Plugins (via `directory.json`). See the repository for instructions.