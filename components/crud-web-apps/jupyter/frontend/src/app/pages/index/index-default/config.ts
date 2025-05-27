import {
  PropertyValue,
  StatusValue,
  ActionListValue,
  ActionIconValue,
  ActionButtonValue,
  ComponentValue,
  TableConfig,
  DateTimeValue,
  LinkValue,
  LinkType,
  MemoryValue,
  quantityToScalar,
} from 'kubeflow';
import { ServerTypeComponent } from './server-type/server-type.component';

// --- Config for the Resource Table ---
export const defaultConfig: TableConfig = {
  dynamicNamespaceColumn: false,
  columns: [
    {
      matHeaderCellDef: $localize`Status`,
      matColumnDef: 'status',
      value: new StatusValue(),
      sort: true,
    },
    {
      matHeaderCellDef: $localize`Name`,
      matColumnDef: 'name',
      style: { width: '20%' },
      value: new LinkValue({
        field: 'link',
        popoverField: 'name',
        truncate: true,
        linkType: LinkType.Internal,
      }),
      sort: true,
    },
    {
      matHeaderCellDef: $localize`Owner`,
      matColumnDef: 'Owner',
      style: { width: '10%' },
      value: new PropertyValue({
        field: 'owner',
        popoverField: 'owner',
        truncate: true,
      }),
      sort: true,
    },
    {
      matHeaderCellDef: $localize`Type`,
      matColumnDef: 'type',
      value: new ComponentValue({
        component: ServerTypeComponent,
      }),
      sort: true,
      sortingPreprocessorFn: element => element.serverType,
      filteringPreprocessorFn: element => {
        if (element.serverType === 'container') {
          return 'container';
        } else if (element.serverType === 'group-one') {
          return 'vscode Visual Studio Code';
        } else if (element.serverType === 'group-two') {
          return 'rstudio';
        } else {
          return 'jupyterlab';
        }
      },
    },
    {
      matHeaderCellDef: $localize`Created at`,
      matColumnDef: 'age',
      style: { width: '12%' },
      textAlignment: 'right',
      value: new DateTimeValue({ field: 'age' }),
      sort: true,
    },
    {
      matHeaderCellDef: $localize`Last activity`,
      matColumnDef: 'last_activity',
      textAlignment: 'right',
      value: new DateTimeValue({ field: 'last_activity' }),
      sort: true,
    },
    {
      matHeaderCellDef: $localize`Image`,
      matColumnDef: 'image',
      style: { width: '20%' },
      value: new PropertyValue({
        field: 'shortImage',
        popoverField: 'image',
        truncate: true,
        style: { maxWidth: '250px' },
      }),
      sort: true,
    },
    {
      matHeaderCellDef: $localize`GPUs`,
      matColumnDef: 'gpus',
      style: { width: '5%' },
      textAlignment: 'right',
      value: new PropertyValue({
        field: 'gpus.count',
        tooltipField: 'gpus.message',
      }),
      sort: true,
    },
    {
      matHeaderCellDef: $localize`CPUs`,
      matColumnDef: 'cpu',
      style: { width: '5%' },
      textAlignment: 'right',
      value: new PropertyValue({ field: 'cpu' }),
      sort: true,
      sortingPreprocessorFn: quantityToScalar,
    },
    {
      matHeaderCellDef: $localize`Memory`,
      matColumnDef: 'memory',
      style: { width: '8%' },
      textAlignment: 'right',
      value: new MemoryValue({
        field: 'memory',
      }),
      sort: true,
    },
    {
      matHeaderCellDef: $localize`IP address`,
      matColumnDef: 'ip',
      style: { width: '11%' },
      textAlignment: 'right',
      value: new PropertyValue({
        field: 'ip',
        popoverField: 'ip',
        truncate: true,
      }),
      sort: true,
    },

    {
      matHeaderCellDef: '',
      matColumnDef: 'actions',
      value: new ActionListValue([
        new ActionButtonValue({
          name: 'connect',
          tooltip: $localize`Connect to this notebook server`,
          color: 'primary',
          field: 'connectAction',
          text: $localize`CONNECT`,
        }),
        new ActionButtonValue({
          name: 'ssh',
          tooltip: $localize`SSH to this notebook server`,
          color: 'primary',
          field: 'sshAction',
          text: $localize`ENABLE SSH`,
        }),
        new ActionButtonValue({
          name: 'port-forward',
          tooltip: $localize`Enable external access by port-forwarding`,
          color: 'primary',
          field: 'portForwardAction',
          text: $localize`PORT FORWARD`,
        }),
        new ActionIconValue({
          name: 'start-stop',
          tooltipInit: $localize`Stop this notebook server`,
          tooltipReady: $localize`Start this notebook server`,
          color: '',
          field: 'startStopAction',
          iconInit: 'material:stop',
          iconReady: 'material:play_arrow',
        }),
        new ActionIconValue({
          name: 'delete',
          tooltip: $localize`Delete this notebook server`,
          color: '',
          field: 'deleteAction',
          iconReady: 'material:delete',
        }),
      ]),
    },
  ],
};
