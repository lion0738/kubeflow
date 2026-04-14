import '@polymer/iron-ajax/iron-ajax.js';
import '@polymer/iron-icon/iron-icon.js';
import '@polymer/iron-icons/iron-icons.js';
import '@polymer/iron-icons/social-icons.js';
import '@polymer/paper-button/paper-button.js';
import '@polymer/paper-toast/paper-toast.js';
import '@polymer/paper-ripple/paper-ripple.js';
import '@polymer/paper-item/paper-icon-item.js';
import '@polymer/paper-icon-button/paper-icon-button.js';
import '@vaadin/vaadin-grid/vaadin-grid.js';
import '@vaadin/vaadin-grid/vaadin-grid-selection-column.js';
import '@vaadin/vaadin-grid/vaadin-grid-sort-column.js';
import '@vaadin/vaadin-grid/theme/material/vaadin-grid-styles.js';

import {html, PolymerElement} from '@polymer/polymer';

import css from './manage-users-view.css';
import template from './manage-users-view.pug';

import './manage-users-view-contributor.js';
import './manage-users-view-secret.js';
import './resources/md2-input/md2-input.js';
import utilitiesMixin from './utilities-mixin.js';

export class ManageUsersView extends utilitiesMixin(PolymerElement) {
    static get template() {
        return html([`
            <style>${css.toString()}</style>
            ${template()}
        `]);
    }

    /**
     * Object describing property-related metadata used by Polymer features
     */
    static get properties() {
        return {
            user: {type: String, value: 'Loading...'},
            isClusterAdmin: {type: Boolean, value: false},
            namespaces: Array,
            hasNamespaces: {type: Boolean, value: false},
            ownedNamespaces: {type: Array, value: []},
            editNamespaces: {type: Array, value: []},
            viewNamespaces: {type: Array, value: []},
            showPasswordForm: {type: Boolean, value: false},
            passwordForm: {
                type: Object,
                value: () => ({
                    currentPassword: '',
                    newPassword: '',
                    confirmPassword: '',
                }),
            },
            passwordFormError: {type: String, value: ''},
            passwordFormSuccess: {type: String, value: ''},
            passwordFormToast: {type: String, value: ''},
            showNamespaceForm: {type: Boolean, value: false},
            newProfileName: {type: String, value: ''},
            namespaceFormError: {type: String, value: ''},
            namespaceActionToast: {type: String, value: ''},
        };
    }
    /**
     * Main ready method for Polymer Elements.
     */
    ready() {
        super.ready();
    }
    namespaceRows(ownedNamespaces, editNamespaces, viewNamespaces) {
        return [
            ...ownedNamespaces.map((ns) => ({
                roleLabel: 'Owner',
                namespace: ns.namespace,
                canDelete: true,
            })),
            ...editNamespaces.map((ns) => ({
                roleLabel: 'Contributor',
                namespace: ns.namespace,
                canDelete: false,
            })),
            ...viewNamespaces.map((ns) => ({
                roleLabel: 'Viewer',
                namespace: ns.namespace,
                canDelete: false,
            })),
        ];
    }
    /**
     * Takes an event from iron-ajax and isolates the error from a request that
     * failed
     * @param {IronAjaxEvent} e
     * @return {string}
     */
    _isolateErrorFromIronRequest(e) {
        const bd = e.detail.request.response||{};
        return bd.error || e.detail.error || e.detail;
    }
    /**
     * Iron-Ajax error handler for getContributors
     * @param {IronAjaxEvent} e
     */
    onAllNamespaceFetchError(e) {
        const error = this._isolateErrorFromIronRequest(e);
        this.allNamespaceError = error;
        this.$.AllNamespaceError.show();
    }
    /**
     * [ComputedProp] Should the ajax call for all namespaces run?
     * @param {boolean} isClusterAdmin
     * @return {boolean}
     */
    shouldFetchAllNamespaces(isClusterAdmin) {
        return isClusterAdmin;
    }

    passwordToggleLabel(showPasswordForm) {
        return showPasswordForm ? 'Hide Password Form' : 'Change Password';
    }

    togglePasswordForm() {
        this.showPasswordForm = !this.showPasswordForm;
        if (!this.showPasswordForm) {
            this._resetPasswordForm();
        }
    }

    cancelPasswordForm() {
        this.showPasswordForm = false;
        this._resetPasswordForm();
    }

    _validatePasswordPolicy(currentPassword, newPassword) {
        if (newPassword.length < 8) {
            return 'New password must be at least 8 characters long.';
        }
        return '';
    }

    async submitPasswordChange() {
        const {
            currentPassword,
            newPassword,
            confirmPassword,
        } = this.passwordForm;
        this.passwordFormSuccess = '';
        if (!currentPassword || !newPassword || !confirmPassword) {
            this.passwordFormError = 'Fill in all password fields.';
            return;
        }
        const policyError = this._validatePasswordPolicy(
            currentPassword,
            newPassword,
        );
        if (policyError) {
            this.passwordFormError = policyError;
            return;
        }
        if (newPassword !== confirmPassword) {
            this.passwordFormError =
                'New password and confirmation do not match.';
            return;
        }

        this.passwordFormError = '';
        try {
            const result = await fetch('/account/api/user/change_password', {
                method: 'POST',
                credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    current_password: currentPassword,
                    new_password: newPassword,
                }),
            });
            const responseText = await result.text();
            if (!result.ok || responseText.includes('Error:')) {
                this.passwordFormError =
                    this._extractPasswordChangeError(responseText);
                return;
            }

            this.passwordFormSuccess = 'Password updated successfully.';
            this.passwordFormToast = 'Password updated successfully.';
            this.$.PasswordFormToast.show();
            this._resetPasswordFormFields();
        } catch (err) {
            this.passwordFormError =
                err.message || 'Failed to update password.';
        }
    }

    _extractPasswordChangeError(responseText) {
        const message = (responseText || '').trim();
        if (!message) {
            return 'Failed to update password.';
        }

        const errorLine = message
            .split('\n')
            .find((line) => line.includes('Error:') || line.includes('error'));
        if (errorLine) {
            return errorLine
                .replace(/^data:\s*/u, '')
                .replace(/^Error:\s*/u, '');
        }
        return message.replace(/^data:\s*/u, '');
    }

    _resetPasswordFormFields() {
        this.passwordForm = {
            currentPassword: '',
            newPassword: '',
            confirmPassword: '',
        };
    }

    _resetPasswordForm() {
        this._resetPasswordFormFields();
        this.passwordFormError = '';
        this.passwordFormSuccess = '';
    }

    namespaceToggleLabel(showNamespaceForm) {
        return showNamespaceForm ? 'Hide Add Namespace' : 'Add Namespace';
    }

    toggleNamespaceForm() {
        this.showNamespaceForm = !this.showNamespaceForm;
        if (!this.showNamespaceForm) {
            this._resetNamespaceForm();
        }
    }

    cancelNamespaceForm() {
        this.showNamespaceForm = false;
        this._resetNamespaceForm();
    }

    _resetNamespaceForm() {
        this.newProfileName = '';
        this.namespaceFormError = '';
    }

    _validateProfileName(profileName) {
        if (!profileName) {
            return 'Fill in a namespace name.';
        }
        if (!/^[a-z](?:[a-z-]*[a-z])?$/.test(profileName)) {
            return 'Namespace name must use lowercase letters and dashes ' +
                'only, and cannot start or end with a dash.';
        }
        return '';
    }

    async submitNamespaceCreate() {
        const profileName = (this.newProfileName || '').trim();
        const validationError = this._validateProfileName(profileName);
        if (validationError) {
            this.namespaceFormError = validationError;
            return;
        }

        this.namespaceFormError = '';
        try {
            const result = await fetch('/account/api/user/add_profile', {
                method: 'POST',
                credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({profile_name: profileName}),
            });
            const responseText = await result.text();
            if (!result.ok || responseText.includes('Error:')) {
                this.namespaceFormError =
                    this._extractScriptError(
                        responseText,
                        'Failed to create namespace.',
                    );
                return;
            }

            this.namespaceActionToast =
                `Namespace '${profileName}' created successfully.`;
            this.$.NamespaceActionToast.show();
            await this.sleep(600);
            window.location.reload();
        } catch (err) {
            this.namespaceFormError =
                err.message || 'Failed to create namespace.';
        }
    }

    async handleDeleteNamespace(event) {
        const profileName = event.model.item.namespace;
        // eslint-disable-next-line no-alert
        const confirmed = window.confirm(
            `Deleting namespace '${profileName}' will remove all data ` +
            'in this namespace. Continue?'
        );
        if (!confirmed) {
            return;
        }

        // eslint-disable-next-line no-alert
        const confirmationInput = window.prompt(
            `Type '${profileName}' to confirm deletion of this namespace.`,
            ''
        );
        if (confirmationInput !== profileName) {
            this.namespaceActionToast =
                'Namespace deletion cancelled. Confirmation text ' +
                'did not match.';
            this.$.NamespaceActionToast.show();
            return;
        }

        try {
            const result = await fetch('/account/api/user/delete_profile', {
                method: 'POST',
                credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({profile_name: profileName}),
            });
            const responseText = await result.text();
            if (!result.ok || responseText.includes('Error:')) {
                this.namespaceActionToast =
                    this._extractScriptError(
                        responseText,
                        'Failed to delete namespace.',
                    );
                this.$.NamespaceActionToast.show();
                return;
            }

            this.namespaceActionToast =
                `Namespace '${profileName}' deleted successfully.`;
            this.$.NamespaceActionToast.show();
            await this.sleep(600);
            window.location.reload();
        } catch (err) {
            this.namespaceActionToast =
                err.message || 'Failed to delete namespace.';
            this.$.NamespaceActionToast.show();
        }
    }

    _extractScriptError(responseText, fallbackMessage) {
        const message = (responseText || '').trim();
        if (!message) {
            return fallbackMessage;
        }

        const errorLine = message
            .split('\n')
            .find((line) => line.includes('Error:') || line.includes('error'));
        if (errorLine) {
            return errorLine
                .replace(/^data:\s*/u, '')
                .replace(/^Error:\s*/u, '');
        }
        return message.replace(/^data:\s*/u, '');
    }
}

customElements.define('manage-users-view', ManageUsersView);
