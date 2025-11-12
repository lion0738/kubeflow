import { Component, OnDestroy, OnInit } from '@angular/core';
import {
  NamespaceService,
  STATUS_TYPE,
  ToolbarButton,
  PollerService,
  Status,
  SnackBarService,
  SnackType,
} from 'kubeflow';
import { JWABackendService } from 'src/app/services/backend.service';
import { Subscription } from 'rxjs';
import { NotebookRawObject } from 'src/app/types';
import { ActivatedRoute, Router } from '@angular/router';
import {
  V1Pod,
  V1ObjectMeta,
  V1PodSpec,
} from '@kubernetes/client-node';
import { ActionsService } from 'src/app/services/actions.service';
import { isEqual } from 'lodash-es';
import { ContainerDetail } from 'src/app/types/container';
import { Condition } from 'src/app/types/condition';

@Component({
  selector: 'app-notebook-page',
  templateUrl: './notebook-page.component.html',
  styleUrls: ['./notebook-page.component.scss'],
})
export class NotebookPageComponent implements OnInit, OnDestroy {
  public notebookName: string;
  public namespace: string;
  public notebook: NotebookRawObject;
  public notebookPod: V1Pod;
  public notebookInfoLoaded = false;
  public podRequestCompleted = false;
  public podRequestError = '';
  public selectedTab = { index: 0, name: 'overview' };
  public buttonsConfig: ToolbarButton[] = [];
  public pageTitle = 'Notebook details';

  pollSubNotebook = new Subscription();
  pollSubPod = new Subscription();
  private resourceType: 'notebook' | 'container' = 'notebook';
  private containerDetail: ContainerDetail;
  private connectInProgress = false;

  constructor(
    public ns: NamespaceService,
    public backend: JWABackendService,
    public poller: PollerService,
    public router: Router,
    public actions: ActionsService,
    public snackBar: SnackBarService,
    private route: ActivatedRoute,
  ) {}

  ngOnInit(): void {
    this.route.params.subscribe(params => {
      const routeData = this.route.snapshot.data || {};
      this.resourceType =
        (routeData.resourceType as 'notebook' | 'container') || 'notebook';
      this.pageTitle = this.isContainer
        ? 'Container details'
        : 'Notebook details';

      this.ns.updateSelectedNamespace(params.namespace);

      this.notebookName = params.notebookName || params.name;
      this.namespace = params.namespace;

      this.poll(this.namespace, this.notebookName);
    });

    this.route.queryParams.subscribe(params => {
      this.selectedTab.name = params.tab;
      this.selectedTab.index = this.switchTab(this.selectedTab.name).index;
      this.selectedTab.name = this.switchTab(this.selectedTab.name).name;
    });
  }

  ngOnDestroy() {
    this.pollSubNotebook.unsubscribe();
    this.pollSubPod.unsubscribe();
  }

  get isContainer(): boolean {
    return this.resourceType === 'container';
  }

  private poll(namespace: string, notebook: string) {
    this.pollSubNotebook.unsubscribe();

    if (this.isContainer) {
      const request = this.backend.getContainer(namespace, notebook);
      this.pollSubNotebook = this.poller.exponential(request).subscribe(
        detail => {
          this.containerDetail = detail;
          this.notebook = this.processIncomingData(
            this.mapContainerDetail(detail),
          );
          this.notebookPod = detail.pod || null;
          this.podRequestCompleted = true;
          this.podRequestError = '';
          this.updateButtons();
          this.notebookInfoLoaded = true;
        },
        error => {
          this.podRequestError = error;
          this.notebookInfoLoaded = true;
          this.podRequestCompleted = true;
        },
      );
      return;
    }

    const request = this.backend.getNotebook(namespace, notebook);

    this.pollSubNotebook = this.poller.exponential(request).subscribe(nb => {
      this.notebook = this.processIncomingData(nb);
      this.getNotebookPod(nb);
      this.updateButtons();
      this.notebookInfoLoaded = true;
    });
  }

  private processIncomingData(notebook: NotebookRawObject) {
    const notebookCopy = JSON.parse(
      JSON.stringify(notebook),
    ) as NotebookRawObject;

    return notebookCopy;
  }

  private switchTab(name): { index: number; name: string } {
    if (name === 'yaml') {
      return { index: 3, name: 'yaml' };
    } else if (name === 'events') {
      return { index: 2, name: 'events' };
    } else if (name === 'logs') {
      return { index: 1, name: 'logs' };
    } else {
      return { index: 0, name: 'overview' };
    }
  }

  public onTabChange(c) {
    const queryParams = { tab: c.tab.textLabel.toLowerCase() };
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams,
      replaceUrl: true,
      queryParamsHandling: '',
    });
  }

  private getNotebookPod(notebook: NotebookRawObject) {
    this.pollSubPod.unsubscribe();

    const request = this.backend.getNotebookPod(notebook);

    this.pollSubPod = this.poller.exponential(request).subscribe(
      pod => {
        this.notebookPod = pod;
        this.podRequestCompleted = true;
      },
      error => {
        this.podRequestError = error;
        this.notebookPod = null;
        this.podRequestCompleted = true;
      },
    );
  }

  navigateBack() {
    this.router.navigate(['/']);
  }

  get status(): Status {
    return this.notebook?.processed_status;
  }

  private updateButtons() {
    if (!this.notebook || !this.status) {
      return;
    }

    const buttons: ToolbarButton[] = [];
    const connectTooltip = this.isContainer
      ? 'Connect to this container'
      : 'Connect to this notebook';
    const connectDisabled =
      this.status?.phase !== STATUS_TYPE.READY || this.connectInProgress;

    buttons.push(
      new ToolbarButton({
        text: 'CONNECT',
        icon: 'developer_board',
        disabled: connectDisabled,
        tooltip: connectTooltip,
        fn: () => {
          this.connectToServer();
        },
      }),
    );
    if (this.status?.phase === 'stopped') {
      buttons.push(
        new ToolbarButton({
          text: 'START',
          icon: 'play_arrow',
          tooltip: this.isContainer ? 'Start this container' : 'Start this notebook',
          fn: () => {
            this.startServer();
          },
        }),
      );
    } else {
      buttons.push(
        new ToolbarButton({
          text: 'STOP',
          icon: 'stop',
          disabled:
            this.status?.phase === STATUS_TYPE.TERMINATING ? true : false,
          tooltip: this.isContainer ? 'Stop this container' : 'Stop this notebook',
          fn: () => {
            this.stopServer();
          },
        }),
      );
    }
    buttons.push(
      new ToolbarButton({
        text: 'DELETE',
        icon: 'delete',
        disabled: this.status?.phase === STATUS_TYPE.TERMINATING ? true : false,
        tooltip: this.isContainer ? 'Delete this container' : 'Delete this notebook',
        fn: () => {
          this.deleteServer();
        },
      }),
    );
    if (isEqual(buttons, this.buttonsConfig)) {
      return;
    }
    this.buttonsConfig = buttons;
  }

  private deleteServer() {
    const delete$ = this.isContainer
      ? this.actions.deleteContainer(this.namespace, this.notebookName)
      : this.actions.deleteNotebook(this.namespace, this.notebookName);

    delete$.subscribe(result => {
      if (result === 'fail') {
        return;
      }
      this.router.navigate(['']);
    });
  }

  private connectToServer() {
    if (this.isContainer) {
      const command = window.prompt(
        'Enter the command to run in the container',
        'bash',
      );
      if (command === null) {
        return;
      }
      this.connectInProgress = true;
      this.updateButtons();
      this.actions
        .connectToContainer(this.namespace, this.notebookName, command)
        .subscribe({
          next: () => {
            this.connectInProgress = false;
            this.updateButtons();
          },
          error: err => {
            const message =
              typeof err === 'string'
                ? err
                : err?.message || 'Failed to open CloudShell session.';
            this.snackBar.open({
              data: {
                msg: message,
                snackType: SnackType.Error,
              },
              duration: 5000,
            });
            this.connectInProgress = false;
            this.updateButtons();
          },
        });
      return;
    }

    this.actions.connectToNotebook(this.namespace, this.notebookName);
  }

  private startServer() {
    const start$ = this.isContainer
      ? this.actions.startContainer(this.namespace, this.notebookName)
      : this.actions.startNotebook(this.namespace, this.notebookName);

    start$.subscribe(_ => {
      this.poll(this.namespace, this.notebookName);
    });
  }

  private stopServer() {
    const stop$ = this.isContainer
      ? this.actions.stopContainer(this.namespace, this.notebookName)
      : this.actions.stopNotebook(this.namespace, this.notebookName);

    stop$.subscribe(_ => {
      this.poll(this.namespace, this.notebookName);
    });
  }

  private mapContainerDetail(detail: ContainerDetail): NotebookRawObject {
    const deployment = detail.deployment;
    const creationTimestampSource =
      deployment.metadata?.creationTimestamp ||
      (detail.summary.age ? new Date(detail.summary.age) : undefined) ||
      new Date();

    const templateSpec: V1PodSpec =
      deployment.spec?.template?.spec || ({} as V1PodSpec);
    const mainContainerName =
      templateSpec?.containers?.[0]?.name || detail.summary.name;

    const metadata: V1ObjectMeta = {
      ...(deployment.metadata || {}),
      name: mainContainerName,
      namespace: detail.summary.namespace,
      annotations: {
        ...(deployment.metadata?.annotations || {}),
        'notebooks.kubeflow.org/server-type': 'container',
        'notebooks.kubeflow.org/creator': detail.summary.owner || '',
      },
      labels: {
        ...(deployment.metadata?.labels || {}),
        'notebook-name': mainContainerName,
      },
      creationTimestamp:
        creationTimestampSource instanceof Date
          ? creationTimestampSource
          : new Date(creationTimestampSource),
    };

    const podConditions: Condition[] =
      detail.pod?.status?.conditions?.map(condition => ({
        lastProbeTime: condition.lastProbeTime
          ? new Date(condition.lastProbeTime).toISOString()
          : '',
        lastTransitionTime: condition.lastTransitionTime
          ? new Date(condition.lastTransitionTime).toISOString()
          : '',
        message: condition.message,
        reason: condition.reason,
        status: condition.status,
        type: condition.type,
      })) || [];

    return {
      apiVersion: deployment.apiVersion || 'apps/v1',
      kind: deployment.kind || 'Deployment',
      metadata,
      spec: {
        template: {
          spec: templateSpec,
        },
      },
      status: {
        conditions: podConditions,
        containerState:
          detail.pod?.status?.containerStatuses?.[0]?.state || null,
        readyReplicas: deployment.status?.readyReplicas || 0,
      },
      processed_status: detail.status,
    };
  }
}
