import '@polymer/iron-ajax/iron-ajax.js';
import '@polymer/iron-icon/iron-icon.js';
import '@polymer/iron-icons/iron-icons.js';
import '@polymer/iron-icons/social-icons.js';
import '@polymer/paper-toast/paper-toast.js';
import '@polymer/paper-ripple/paper-ripple.js';
import '@polymer/paper-item/paper-icon-item.js';
import '@polymer/paper-icon-button/paper-icon-button.js';

import {html, PolymerElement} from '@polymer/polymer';

import './resources/paper-chip.js';
import './resources/md2-input/md2-input.js';
import css from './manage-users-view-secret.css';
import template from './manage-users-view-secret.pug';
import utilitiesMixin from './utilities-mixin.js';

export class ManageUsersViewSecret extends utilitiesMixin(PolymerElement) {
  static get template() {
    return html([`
      <style>${css.toString()}</style>
      ${template()}
    `]);
  }

  static get properties() {
    return {
      ownedNamespace: {type: Object, value: () => ({})},
      newSecret: {
        type: Object,
        value: () => ({
            name: '',
            registry: '',
            username: '',
            password: '',
            email: ''
        }),
      },
      secretList: {type: Array, value: () => []},
      secretError: Object,
      selectedSecretName: String,
    };
  }

  ready() {
    super.ready();
  }

  createRegistrySecret() {
    const api = this.$.CreateSecretAjax;
    api.body = {
        namespace: this.ownedNamespace.namespace,
        name: this.newSecret.name,
        registry: this.newSecret.registry,
        username: this.newSecret.username,
        password: this.newSecret.password,
        email: this.newSecret.email,
    };
    api.generateRequest();
  }

  handleSecretCreate(e) {
    if (e.detail.error) {
      const error = this._isolateErrorFromIronRequest(e);
      this.secretError = error;
      return;
    }
    this.newSecret = {
        name: '',
        registry: '',
        username: '',
        password: '',
        email: '',
    };
    this.$.ListSecretsAjax.generateRequest();
  }

  deleteRegistrySecret(e) {
    const name = e.model.item;
    this.selectedSecretName = name;
    this.$.DeleteSecretAjax.generateRequest();
  }

  handleSecretDelete(e) {
    if (e.detail.error) {
      const error = this._isolateErrorFromIronRequest(e);
      this.secretError = error;
      return;
    }
    this.$.ListSecretsAjax.generateRequest();
  }

  onSecretFetchError(e) {
    const error = this._isolateErrorFromIronRequest(e);
    this.secretError = error;
    this.$.SecretError.show();
  }

  _isolateErrorFromIronRequest(e) {
    let bd = {};
    if (e.detail && e.detail.request && e.detail.request.response) {
        bd = e.detail.request.response;
    }
    return bd.error || e.detail.error || e.detail;
  }
}

customElements.define('manage-users-view-secret', ManageUsersViewSecret);
