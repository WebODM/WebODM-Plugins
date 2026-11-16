import React from 'react';
import ReactDOM from 'ReactDOM';
import Standby from 'webodm/components/Standby';
import PropTypes from 'prop-types';
import $ from 'jquery';
import { _, interpolate } from 'webodm/classes/gettext';
import Workers from 'webodm/classes/Workers';

const SCOPE = "https://www.googleapis.com/auth/drive.file";
const FOLDER_MIME = "application/vnd.google-apps.folder";
const FILE_FIELDS = "id,name,mimeType,size,imageMediaMetadata(location,time)";
const DRIVE_API = "https://www.googleapis.com/drive/v3/files";

let scriptsPromise = null;
const TOKEN_KEY = "gdrive_token";
let accessToken = null;

function clearToken(){
  accessToken = null;
  try{
    sessionStorage.removeItem(TOKEN_KEY);
  }catch(e){}
}

function loadScript(src){
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.async = true;
    s.onload = resolve;
    s.onerror = () => reject(new Error(interpolate(_("Cannot load %(url)s"), {url: src})));
    document.head.appendChild(s);
  });
}

function loadGoogleScripts(){
  if (!scriptsPromise){
    scriptsPromise = Promise.all([
      loadScript("https://accounts.google.com/gsi/client"),
      loadScript("https://apis.google.com/js/api.js").then(() => new Promise(resolve => window.gapi.load("picker", resolve)))
    ]).catch(e => {
      scriptsPromise = null;
      throw e;
    });
  }
  return scriptsPromise;
}

function parseExifTime(time){
  if (!time) return null;
  const m = time.match(/^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})/);
  if (!m) return null;
  const t = new Date(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}`).getTime();
  return isNaN(t) ? null : t;
}

function driveGet(url, token, asBlob = false){
  return fetch(url, { headers: { Authorization: `Bearer ${token}` } }).then(res => {
    if (res.status === 401) clearToken();
    if (!res.ok) throw new Error(interpolate(_("Google Drive request failed (%(status)s)"), {status: res.status}));
    return asBlob ? res.blob() : res.json();
  });
}

function listFolder(folderId, token){
  const files = [];
  const q = encodeURIComponent(`'${folderId}' in parents and trashed = false and mimeType != '${FOLDER_MIME}'`);

  const page = pageToken => {
    let url = `${DRIVE_API}?q=${q}&pageSize=1000&fields=nextPageToken,files(${FILE_FIELDS})&supportsAllDrives=true&includeItemsFromAllDrives=true`;
    if (pageToken) url += `&pageToken=${encodeURIComponent(pageToken)}`;

    return driveGet(url, token).then(res => {
      files.push(...(res.files || []));
      return res.nextPageToken ? page(res.nextPageToken) : files;
    });
  };

  return page("");
}

function getFiles(ids, token){
  const files = [];
  const queue = ids.slice();

  const worker = () => {
    if (!queue.length) return Promise.resolve();
    const id = queue.shift();
    return driveGet(`${DRIVE_API}/${id}?fields=${FILE_FIELDS}&supportsAllDrives=true`, token).then(f => {
      files.push(f);
      return worker();
    });
  };

  return Promise.all([1, 2, 3, 4, 5, 6].map(worker)).then(() => files);
}

function isAcceptedFile(name, mimeType, acceptedFiles){
  name = (name || "").toLowerCase();
  mimeType = (mimeType || "").toLowerCase();

  return acceptedFiles.split(",").some(rule => {
    rule = rule.trim().toLowerCase();
    if (rule[0] === ".") return name.endsWith(rule);
    if (rule.endsWith("/*")) return mimeType.indexOf(rule.slice(0, -1)) === 0;
    return mimeType === rule;
  });
}

function getMaxImages(){
  return new Promise((resolve, reject) => {
    $.getJSON("/api/processingnodes/").done(nodes => {
      if (!nodes.length){
        resolve(null);
        return;
      }

      let max = 0;
      for (let i = 0; i < nodes.length; i++){
        if (nodes[i].max_images === null){
          resolve(null);
          return;
        }
        max = Math.max(max, nodes[i].max_images);
      }
      resolve(max);
    }).fail(() => reject(new Error(_("Cannot retrieve processing nodes"))));
  });
}

function uniqueName(name, used){
  if (!used[name]){
    used[name] = 1;
    return name;
  }

  const idx = name.lastIndexOf(".");
  const base = idx !== -1 ? name.substring(0, idx) : name;
  const ext = idx !== -1 ? name.substring(idx) : "";
  let candidate;
  do{
    candidate = `${base}_${used[name]++}${ext}`;
  }while(used[candidate]);
  used[candidate] = 1;
  return candidate;
}

export default class GDriveSource extends React.Component {
  static propTypes = {
    projectId: PropTypes.number.isRequired,
    acceptedFiles: PropTypes.string.isRequired,
    onFilesSelected: PropTypes.func.isRequired,
    userId: PropTypes.string.isRequired,
    clientId: PropTypes.string,
    apiKey: PropTypes.string,
    appId: PropTypes.string
  }

  state = {
    loading: false
  }

  preload = () => {
    loadGoogleScripts().catch(e => console.warn(e));
  }

  tokenOwner = () => `${this.props.userId}:${this.props.clientId}`

  requestToken = () => {
    return new Promise((resolve, reject) => {
      const client = window.google.accounts.oauth2.initTokenClient({
        client_id: this.props.clientId,
        scope: SCOPE,
        callback: res => {
          if (res.error){
            reject(new Error(res.error_description || res.error));
            return;
          }
          accessToken = {
            owner: this.tokenOwner(),
            value: res.access_token,
            expires: Date.now() + parseInt(res.expires_in) * 1000
          };
          try{
            sessionStorage.setItem(TOKEN_KEY, JSON.stringify(accessToken));
          }catch(e){}
          resolve(accessToken.value);
        },
        error_callback: err => {
          if (err.type === "popup_closed") reject(null);
          else if (err.type === "popup_failed_to_open") reject(new Error(_("Cannot open the Google sign-in window. Please allow popups for this site.")));
          else reject(new Error(err.message || err.type));
        }
      });
      client.requestAccessToken({prompt: ""});
    });
  }

  getToken = (minValidityMs) => {
    if (!accessToken){
      try{
        const t = JSON.parse(sessionStorage.getItem(TOKEN_KEY));
        if (t && t.owner === this.tokenOwner() && t.value && t.expires > Date.now()) accessToken = t;
      }catch(e){}
    }

    const t = accessToken;
    if (t && t.owner === this.tokenOwner() && t.expires - Date.now() > minValidityMs) return Promise.resolve(t.value);
    return this.requestToken();
  }

  handleClick = () => {
    loadGoogleScripts()
      .then(() => this.getToken(30 * 60 * 1000))
      .then(token => this.showPicker(token))
      .catch(this.handleError);
  }

  handleError = e => {
    this.setState({loading: false});
    if (!e) return;
    this.props.onFilesSelected(e.message || String(e));
  }

  showPicker = (token) => {
    const picker = window.google.picker;
    const view = new picker.DocsView(picker.ViewId.DOCS)
      .setIncludeFolders(true)
      .setSelectFolderEnabled(true)
      .setMode(picker.DocsViewMode.LIST);

    new picker.PickerBuilder()
      .addView(view)
      .enableFeature(picker.Feature.MULTISELECT_ENABLED)
      .setOAuthToken(token)
      .setDeveloperKey(this.props.apiKey)
      .setAppId(this.props.appId)
      .setTitle(_("Select images, GCP files or a folder"))
      .setCallback(data => {
        if (data.action === picker.Action.PICKED){
          this.setState({loading: true});
          this.handlePicked(data.docs || [], token).catch(this.handleError);
        }
      })
      .build()
      .setVisible(true);
  }

  handlePicked = (docs, token) => {
    const folders = docs.filter(d => d.mimeType === FOLDER_MIME);
    const picked = docs.filter(d => d.mimeType !== FOLDER_MIME);
    const pickedIds = new Set(picked.map(d => d.id));
    const parents = [...new Set(picked.map(d => d.parentId).filter(p => p))];

    return Promise.all([
      getMaxImages(),
      Promise.all(folders.map(f => listFolder(f.id, token))),
      Promise.all(parents.map(p => listFolder(p, token)))
    ]).then(([maxImages, folderFiles, parentFiles]) => {
      const found = {};
      parentFiles.forEach(list => list.forEach(f => {
        if (pickedIds.has(f.id)) found[f.id] = f;
      }));
      const missing = picked.filter(d => !found[d.id]).map(d => d.id);

      return getFiles(missing, token).then(files => [maxImages, folderFiles, Object.values(found).concat(files)]);
    }).then(([maxImages, folderFiles, files]) => {
      for (let i = 0; i < folders.length; i++){
        if (folderFiles[i].length === 0){
          throw new Error(interpolate(_("Cannot read the files in %(folder)s. Open the folder in the Google Drive window and select its files instead."), {folder: folders[i].name}));
        }
      }

      const all = files.concat(...folderFiles).filter(f => isAcceptedFile(f.name, f.mimeType, this.props.acceptedFiles));
      if (all.length === 0) throw new Error(_("None of the selected files can be processed. Select images and GCP files."));

      if (maxImages !== null && all.length > maxImages){
        throw new Error(interpolate(_("You selected %(count)s files, but you can only process at most %(max)s images."), {count: all.length, max: maxImages}));
      }

      const used = {};
      return Promise.all(all.map(f => {
        const name = uniqueName(f.name, used);

        if (f.mimeType.indexOf("text/") === 0){
          return driveGet(`${DRIVE_API}/${f.id}?alt=media&supportsAllDrives=true`, token, true)
            .then(blob => Object.assign(new File([blob], name, {type: f.mimeType}), {driveId: f.id}));
        }

        const meta = f.imageMediaMetadata || {};
        const loc = meta.location;
        const time = parseExifTime(meta.time);
        const exif = loc && loc.latitude !== undefined && loc.longitude !== undefined ? {
          latitude: loc.latitude,
          longitude: loc.longitude,
          GPSAltitude: loc.altitude,
          DateTimeOriginal: time !== null ? new Date(time) : undefined
        } : {};

        return {
          name,
          type: f.mimeType,
          size: parseInt(f.size) || 0,
          driveId: f.id,
          parseExif: () => Promise.resolve(exif)
        };
      }));
    }).then(selected => {
      this.setState({loading: false});
      this.props.onFilesSelected(null, selected, this.upload);
    });
  }

  upload = ({ project, task, files }, cb, onProgress) => {
    let canceled = false;
    let celeryTaskId = null;
    const totalBytes = files.reduce((sum, f) => sum + (f.size || 0), 0);

    const done = error => {
      if (!canceled) cb(error);
    };

    new Promise((resolve, reject) => {
      const t = accessToken;
      if (t && t.owner === this.tokenOwner() && t.expires > Date.now()) resolve(t.value);
      else reject(new Error(_("Google Drive access expired, please select the files again")));
    }).then(token => {
      if (canceled) return;
      $.ajax({
        url: `/api/plugins/gdrive/projects/${project.id}/tasks/${task.id}/import`,
        contentType: 'application/json',
        data: JSON.stringify({
          token,
          files: files.map(f => ({ id: f.driveId, name: f.name, mimeType: f.type, size: f.size }))
        }),
        dataType: 'json',
        type: 'POST'
      }).done(res => {
        if (!res.celery_task_id){
          done(res.error || _("Cannot import files from Google Drive"));
          return;
        }

        celeryTaskId = res.celery_task_id;
        if (canceled){
          Workers.cancel(celeryTaskId);
          return;
        }

        Workers.waitForCompletion(celeryTaskId, done, (status, progress) => {
          if (!canceled) onProgress(progress, progress / 100 * totalBytes, Math.floor(progress / 100 * files.length));
        });
      }).fail(xhr => {
        const detail = xhr.responseJSON && (xhr.responseJSON.detail || xhr.responseJSON[0]);
        done(detail || _("Cannot import files from Google Drive"));
      });
    }).catch(e => done(e ? e.message || String(e) : _("Google sign-in was canceled")));

    return {
      cancel: () => {
        canceled = true;
        if (celeryTaskId) Workers.cancel(celeryTaskId);
      }
    };
  }

  render(){
    return (
      <li>
        <a href="javascript:void(0)" onClick={this.handleClick} onMouseEnter={this.preload} onTouchStart={this.preload}>
          <i className="fab fa-google-drive fa-fw"></i> {_("From Google Drive")}
        </a>
        {this.state.loading ? ReactDOM.createPortal(
          <div className="gdrive-loading">
            <Standby show={true} message={_("Loading files from Google Drive...")} />
          </div>, document.body) : ""}
      </li>
    );
  }
}
