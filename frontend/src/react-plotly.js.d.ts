declare module 'react-plotly.js' {
  import { Component } from 'react';
  import { Data, Layout, Config } from 'plotly.js';

  export interface PlotParams {
    data: Data[];
    layout?: Partial<Layout>;
    config?: Partial<Config>;
    frames?: any[];
    onClick?: (event: any) => void;
    onHover?: (event: any) => void;
    onUnhover?: (event: any) => void;
    onRelayout?: (event: any) => void;
    onSelected?: (event: any) => void;
    onUpdate?: (figure: any, graphDiv: any) => void;
    onInitialized?: (figure: any, graphDiv: any) => void;
    onPurge?: (figure: any, graphDiv: any) => void;
    onError?: (error: any) => void;
    useResizeHandler?: boolean;
    className?: string;
    style?: React.CSSProperties;
    divId?: string;
    revision?: number;
  }

  export default class Plot extends Component<PlotParams> {}
}
