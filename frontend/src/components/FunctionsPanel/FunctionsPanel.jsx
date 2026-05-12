import styles from './FunctionsPanel.module.css';
import RunTile from './RunTile.jsx';
import { runPre, runPipeline, runPost, runFull } from '../../api.js';

const PRE_FIELDS = [
  { key: 'input', label: 'Input CSV', type: 'csv-dropdown' },
  { key: 'state', label: 'State', type: 'text' },
  { key: 'crops', label: 'Crops', type: 'crops' },
  { key: 'output', label: 'Output path', type: 'text' },
  { key: 'keep_intermediate', label: 'Keep intermediate', type: 'checkbox', defaultValue: true },
];

const PIPELINE_FIELDS = [
  { key: 'raw_file', label: 'Raw file', type: 'csv-dropdown' },
  { key: 'crops', label: 'Crops', type: 'crops' },
  { key: 'output_dir', label: 'Output dir', type: 'text', defaultValue: 'outputs/repair' },
  { key: 'model', label: 'Model path', type: 'text', defaultValue: '../models/qwen2.5-7b-instruct' },
  { key: 'api_key', label: 'API key', type: 'password' },
  { key: 'gpu_id', label: 'GPU ID', type: 'number', defaultValue: 1 },
  {
    key: 'grid_mode',
    label: 'Grid mode',
    type: 'select',
    defaultValue: 'quick',
    options: [
      { value: 'quick', label: 'Quick' },
      { value: 'full', label: 'Full' },
    ],
  },
  { key: 'skip_phase1', label: 'Skip phase 1', type: 'checkbox' },
  { key: 'skip_phase2', label: 'Skip phase 2', type: 'checkbox' },
  { key: 'skip_repair', label: 'Skip repair', type: 'checkbox' },
  { key: 'skip_unique_q', label: 'Skip unique-Q', type: 'checkbox' },
  { key: 'skip_corpus_filter', label: 'Skip corpus filter', type: 'checkbox' },
  { key: 'skip_qa_gen', label: 'Skip QA gen', type: 'checkbox' },
];

const POST_FIELDS = [
  { key: 'input', label: 'Input dir', type: 'text', defaultValue: 'outputs/repair' },
  { key: 'skip_collect', label: 'Skip collect', type: 'checkbox' },
  { key: 'skip_dedup', label: 'Skip dedup', type: 'checkbox' },
];

const FULL_FIELDS = [
  { key: 'raw_file', label: 'Raw file', type: 'csv-dropdown' },
  { key: 'state', label: 'State', type: 'text' },
  { key: 'crops', label: 'Crops', type: 'crops' },
  { key: 'output_dir', label: 'Output dir', type: 'text', defaultValue: 'outputs/repair' },
  { key: 'model', label: 'Model path', type: 'text', defaultValue: '../models/qwen2.5-7b-instruct' },
  { key: 'api_key', label: 'API key', type: 'password' },
  { key: 'gpu_id', label: 'GPU ID', type: 'number', defaultValue: 1 },
  {
    key: 'grid_mode',
    label: 'Grid mode',
    type: 'select',
    defaultValue: 'quick',
    options: [
      { value: 'quick', label: 'Quick' },
      { value: 'full', label: 'Full' },
    ],
  },
  { key: 'skip_pre_pipeline', label: 'Skip pre-pipeline', type: 'checkbox' },
  { key: 'skip_qa_gen', label: 'Skip QA gen', type: 'checkbox' },
  { key: 'skip_post_pipeline', label: 'Skip post-pipeline', type: 'checkbox' },
];

export default function FunctionsPanel({ allCsvs }) {
  return (
    <div className={styles.grid}>
      <RunTile
        title="Pre-Pipeline"
        description="Filter state rows and normalise crop names"
        fields={PRE_FIELDS}
        onRun={runPre}
        allCsvs={allCsvs}
      />
      <RunTile
        title="Pipeline"
        description="Run the 7-stage clustering pipeline per crop"
        fields={PIPELINE_FIELDS}
        onRun={runPipeline}
        allCsvs={allCsvs}
      />
      <RunTile
        title="Post-Pipeline"
        description="Collect and deduplicate final outputs"
        fields={POST_FIELDS}
        onRun={runPost}
        allCsvs={allCsvs}
      />
      <RunTile
        title="Full Pipeline"
        description="Pre → pipeline → post in one shot"
        fields={FULL_FIELDS}
        onRun={runFull}
        allCsvs={allCsvs}
      />
    </div>
  );
}
