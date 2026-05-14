import RunTile from './RunTile.jsx';
import { runPre, runPipeline, runPost, runFull } from '../../api.js';

export const CROP_NAMES = [
  'Acid Lime', 'Almond', 'Aloe Vera', 'Amaranthus', 'Aonla', 'Apple', 'Apricot',
  'Arecanut', 'Arum', 'Ash Gourd', 'Avocado', 'Babul', 'Bael', 'Banana',
  'Barnyard Millet', 'Barley', 'Bay Leaf', 'Beekeeping', 'Beetroot', 'Bengal Gram',
  'Ber', 'Berseem', 'Betel Vine', 'Birdwood Grass', "Bishop's Weed", 'Bitter Gourd',
  'Black Gram', 'Bottle Gourd', 'Broad Bean', 'Brinjal', 'Broccoli',
  'Brussels Sprouts', 'Buckwheat', 'Buffel Grass', 'Bush Squash', 'Butter Pea',
  'Cabbage', 'Cardamom', 'Carnation', 'Carrot', 'Castor', 'Cashew', 'Cauliflower',
  'Celery', 'Chapan Kaddu', 'Chestnut', 'Chillies', 'China Aster', 'Chinese Cabbage',
  'Chinar Tree', 'Chrysanthemum', 'Cinnamon', 'Citrus', 'Clove', 'Cluster Bean',
  'Cocoa', 'Coconut', 'Coffee', 'Coleus', 'Colocasia', 'Coriander', 'Cotton',
  'Cowpea', 'Crossandra', 'Cucumber', 'Cumin', 'Curry Leaf', 'Custard Apple',
  'Cymbidium', 'Dhaincha', 'Dharaf Grass', 'Dinanath Grass', 'Dill Seed',
  'Dolichos Bean', 'Drumstick', 'Elephant Foot Yam', 'Eucalyptus', 'Faba Bean',
  'Fennel', 'Fenugreek', 'Fig', 'Finger Millet', 'Fodder Sorghum', 'Foxtail Millet',
  'French Bean', 'Garden Pea', 'Garlic', 'Gerbera', 'Ginger', 'Gladiolus',
  'Golden Timothy', 'Grape', 'Greater Yam', 'Green Gram', 'Groundnut', 'Guar',
  'Guava', 'Guinea Grass', 'Gunda', 'Hemp', 'Hibiscus', 'Honey Plant', 'Horse Gram',
  'Indian Bean', 'Indian Clover', 'Ivy Gourd', 'Jackfruit', 'Jamun', 'Jasmine',
  'Jatropha', 'Jojoba', 'Jute', 'Karan Rai', 'Karonda', 'Kidney Bean', 'Kiwi Fruit',
  'Knol-Khol', 'Kodo Millet', 'Kokum', 'Kolanchi', 'Lablab Bean', 'Large Cardamom',
  'Lathyrus', 'Leafy Vegetable', 'Lehberry', 'Lemon', 'Lentil', 'Lesser Yam',
  'Lettuce', 'Lilies', 'Linseed', 'Litchi', 'Little Millet', 'Long Melon', 'Loquat',
  'Lucerne', 'Maize', 'Mango', 'Marigold', 'Marvel Grass', 'Melon', 'Mesta', 'Mint',
  'Mosambi', 'Moth Bean', 'Mulberry', 'Mushroom', 'Muskmelon', 'Mustard',
  'Napier Grass', 'Neem', 'Niger', 'Nutmeg', 'Oats', 'Oil Palm', 'Okra', 'Oleander',
  'Olive', 'Onion', 'Opium Poppy', 'Orange', 'Paddy', 'Palmyra', 'Papaya',
  'Passion Fruit', 'Pea', 'Peach', 'Pecan Nut', 'Pearl Millet', 'Pear', 'Periwinkle',
  'Persian Clover', 'Persimmon', 'Pigeon Pea', 'Pillipesara', 'Pineapple', 'Plum',
  'Pointed Gourd', 'Pomegranate', 'Poplar', 'Potato', 'Proso Millet', 'Pumpkin',
  'Radish', 'Red Clover', 'Ribbed Gourd', 'Ricebean', 'Ridge Gourd', 'Rocket Salad',
  'Rose', 'Roselle', 'Round Melon', 'Rubber', 'Runner Bean', 'Ryegrass', 'Safed Musli',
  'Safflower', 'Saffron', 'Sal Wood', 'Sandalwood', 'Sapota', 'Sen Grass', 'Sesame',
  'Setaria Grass', 'Shatavari', 'Snap Melon', 'Snake Gourd', 'Sorghum', 'Soybean',
  'Spinach', 'Spine Gourd', 'Sponge Gourd', 'Stevia', 'Strawberry', 'Stylosanthes',
  'Sudan Grass', 'Sugar Beet', 'Sugarcane', 'Summer Squash', 'Sunflower', 'Sunnhemp',
  'Sweet Cherry', 'Sweet Potato', 'Tall Fescue Grass', 'Tapioca', 'Tea', 'Teak',
  'Teosinte', 'Tobacco', 'Tomato', 'Triticale', 'Tuberose', 'Tulsi', 'Tumba',
  'Turmeric', 'Turnip', 'Vanilla', 'Velimasal', 'Walnut', 'Watermelon', 'Wheat',
  'White Clover', 'White Yam', 'Winged Bean', 'Yard Long Bean', 'Zantedeschia',
].filter((v, i, a) => a.indexOf(v) === i).sort();

const GRID_MODE_OPTIONS = [
  { value: 'quick',      label: 'Quick (18 configs)' },
  { value: 'medium',     label: 'Medium (108 configs)' },
  { value: 'full',       label: 'Full (240 configs)' },
  { value: 'exhaustive', label: 'Exhaustive (480 configs)' },
];

const PRE_FIELDS = [
  { key: 'input',            label: 'Input CSV',        type: 'csv-dropdown' },
  { key: 'state',            label: 'State',            type: 'text' },
  { key: 'crops',            label: 'Crops',            type: 'crops-selector' },
  { key: 'output',           label: 'Output path',      type: 'text' },
  { key: 'keep_intermediate',label: 'Keep intermediate',type: 'checkbox', defaultValue: true },
];

const PIPELINE_FIELDS = [
  { key: 'raw_file',  label: 'Raw file', type: 'csv-dropdown' },
  { key: 'crops',     label: 'Crops',    type: 'crops-selector' },
  {
    key: 'grid_mode', label: 'Grid mode', type: 'select',
    defaultValue: 'quick', options: GRID_MODE_OPTIONS,
  },
  { key: 'skip_phase1',       label: 'Skip phase 1',       type: 'checkbox' },
  { key: 'skip_phase2',       label: 'Skip phase 2',       type: 'checkbox' },
  { key: 'skip_repair',       label: 'Skip repair',        type: 'checkbox' },
  { key: 'skip_unique_q',     label: 'Skip unique-Q',      type: 'checkbox' },
  { key: 'skip_corpus_filter',label: 'Skip corpus filter', type: 'checkbox' },
  { key: 'skip_qa_gen',       label: 'Skip QA gen',        type: 'checkbox' },
];

const POST_FIELDS = [
  { key: 'input', label: 'Crop QA folder', type: 'repair-dir-dropdown' },
];

const FULL_FIELDS = [
  { key: 'raw_file', label: 'Raw file', type: 'csv-dropdown' },
  { key: 'state',    label: 'State',    type: 'text' },
  { key: 'crops',    label: 'Crops',    type: 'crops-selector' },
  {
    key: 'grid_mode', label: 'Grid mode', type: 'select',
    defaultValue: 'quick', options: GRID_MODE_OPTIONS,
  },
  { key: 'skip_pre_pipeline',  label: 'Skip pre-pipeline',  type: 'checkbox' },
  { key: 'skip_qa_gen',        label: 'Skip QA gen',        type: 'checkbox' },
  { key: 'skip_post_pipeline', label: 'Skip post-pipeline', type: 'checkbox' },
];

export default function FunctionsPanel({ allCsvs, repairDirs }) {
  return (
    <div className="grid grid-cols-2 gap-4 max-[700px]:grid-cols-1">
      <RunTile
        title="Pre-Pipeline"
        description="Filter state rows and normalise crop names"
        fields={PRE_FIELDS}
        onRun={runPre}
        allCsvs={allCsvs}
        repairDirs={repairDirs}
        cropNames={CROP_NAMES}
      />
      <RunTile
        title="Pipeline"
        description="Run the 7-stage clustering pipeline per crop"
        fields={PIPELINE_FIELDS}
        onRun={runPipeline}
        allCsvs={allCsvs}
        repairDirs={repairDirs}
        cropNames={CROP_NAMES}
      />
      <RunTile
        title="Post-Pipeline"
        description="Collect and deduplicate final outputs"
        fields={POST_FIELDS}
        onRun={runPost}
        allCsvs={allCsvs}
        repairDirs={repairDirs}
        cropNames={CROP_NAMES}
      />
      <RunTile
        title="Full Pipeline"
        description="Pre → pipeline → post in one shot"
        fields={FULL_FIELDS}
        onRun={runFull}
        allCsvs={allCsvs}
        repairDirs={repairDirs}
        cropNames={CROP_NAMES}
      />
    </div>
  );
}
