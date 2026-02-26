# CAN Telemetry Dashboard - User Guide

## 🎉 Dashboard Complete!

Your React + TypeScript dashboard is now fully built and ready to use!

## 📦 What Was Built

### Components Created (21 files)

**Configuration & Setup:**
- `vite.config.ts` - Build configuration with API proxy
- `tailwind.config.ts` - Dark theme styling
- `.env.development` - Environment variables

**API Layer (3 files):**
- `src/api/types.ts` - TypeScript interfaces
- `src/api/client.ts` - Axios HTTP client
- `src/api/hooks.ts` - TanStack Query hooks

**State Management (2 files):**
- `src/store/selectionStore.ts` - Vehicle, time range, signals selection
- `src/store/chartStore.ts` - Chart data and visibility

**Utilities (4 files):**
- `src/utils/colors.ts` - 10-color signal palette
- `src/utils/formatters.ts` - Number, date, byte formatting
- `src/utils/timeRanges.ts` - Time range presets and validation
- `src/utils/chartHelpers.ts` - uPlot configuration and CSV export

**Common Components (5 files):**
- `src/components/common/Button.tsx` - Reusable button with variants
- `src/components/common/Card.tsx` - Container component
- `src/components/common/LoadingSpinner.tsx` - Loading indicator
- `src/components/common/ErrorBanner.tsx` - Error display
- `src/components/common/EmptyState.tsx` - Empty state placeholder

**Layout Components (4 files):**
- `src/components/layout/AppLayout.tsx` - Main grid layout
- `src/components/layout/TopBar.tsx` - Header with health status
- `src/components/layout/Sidebar.tsx` - Collapsible sidebar
- `src/components/layout/MainContent.tsx` - Chart area

**Selector Components (4 files):**
- `src/components/selectors/VehicleSelector.tsx` - Vehicle picker
- `src/components/selectors/TimeRangeSelector.tsx` - Time range picker
- `src/components/selectors/SignalSelector.tsx` - Signal multi-select
- `src/components/selectors/QueryControls.tsx` - Query settings

**Chart Components (4 files):**
- `src/components/chart/TimeSeriesChart.tsx` - uPlot chart (main component)
- `src/components/chart/ChartToolbar.tsx` - Zoom and export controls
- `src/components/chart/ChartLegend.tsx` - Signal visibility toggles
- `src/App.tsx` - Final integrated dashboard

## 🚀 How to Use

### 1. Start the Dashboard

Make sure the backend is running first:
```bash
cd c:\Documents\Telematics\can-telemetry-platform\backend
venv\Scripts\activate
python -m uvicorn src.app:app --reload
```

Then start the frontend:
```bash
cd c:\Documents\Telematics\can-telemetry-platform\frontend
npm run dev
```

Open your browser to: **http://localhost:5173**

### 2. Dashboard Workflow

#### Step 1: Select a Vehicle
- Click on a vehicle card in the sidebar
- If only one vehicle exists, it will be auto-selected
- Vehicle card shows:
  - Vehicle ID (e.g., VEH_001)
  - Date range of data
  - Total frame count

#### Step 2: Choose Time Range
- Click a preset button: **1h, 6h, 24h, or 7d**
- Or click **Custom Range** to pick exact start/end times
- Current selection is displayed at the bottom

#### Step 3: Select Signals
- Expand message groups by clicking them
- Check boxes next to signals you want to visualize
- Color indicator shows the chart line color
- Warning appears when selecting many signals (>8)
- Max 10 signals can be selected

#### Step 4: Adjust Query Settings
- Use the **Max Points** slider (10 - 100,000)
- Default is 2,000 points for smooth performance
- Higher values = more detail but slower rendering

#### Step 5: Load Data
- Click the **Load Data** button
- Wait for the query to complete (may take a few seconds for large datasets)
- Chart will render with all selected signals

#### Step 6: Interact with the Chart
- **Zoom**: Drag horizontally on the chart
- **Pan**: Scroll while hovering over the chart
- **Toggle signals**: Click on signals in the legend below the chart
- **Export CSV**: Click the CSV button in the toolbar
- **Reset view**: Click the reset button

### 3. Advanced Features

**Multi-Y-Axis:**
- Signals with different units get separate Y-axes
- Max 3 Y-axes (left, right, alternating)
- Automatically grouped by unit (voltage, current, temperature, etc.)

**Downsampling:**
- Backend uses LTTB (Largest Triangle Three Buckets) algorithm
- Reduces 50k+ points to your max points setting
- Preserves visual shape while improving performance
- Downsampling info shown in toolbar stats

**Query Stats:**
- Toolbar shows:
  - Rows scanned by Athena
  - Query execution time
  - Downsampling ratio (if applied)

**Sidebar Collapse:**
- Click the menu icon in the top-left to hide/show sidebar
- More space for chart visualization
- Responsive on mobile devices

## 🎨 Color Palette

Signals are assigned colors in this order:
1. Cyan (#06b6d4)
2. Violet (#8b5cf6)
3. Amber (#f59e0b)
4. Emerald (#10b981)
5. Red (#ef4444)
6. Blue (#3b82f6)
7. Pink (#ec4899)
8. Teal (#14b8a6)
9. Orange (#f97316)
10. Indigo (#6366f1)

Colors cycle if you select more than 10 signals.

## 📊 Example Queries

### Battery Pack Monitoring
- Vehicle: VEH_001
- Time: Last 1 Hour
- Signals:
  - Pack_Voltage
  - Pack_Current
  - Pack_SOC
  - Cell_Delta_mV

### Motor Performance
- Vehicle: VEH_001
- Time: Last 24 Hours
- Signals:
  - Motor_RPM
  - Motor_Torque
  - Motor_Power
  - Stator_Temp

### Cooling System
- Vehicle: VEH_001
- Time: Last 6 Hours
- Signals:
  - Coolant_Inlet
  - Coolant_Outlet
  - Flow_Rate
  - Pump_Duty

## 🐛 Troubleshooting

### "Select a vehicle first" message
- Make sure the backend is running
- Check that vehicles are loaded from AWS Athena
- Verify `.env` has `LOCAL_MODE=false` and correct AWS credentials

### Chart not rendering
- Check browser console for errors
- Ensure at least one signal is selected
- Verify the query returned data (check query stats in toolbar)
- Try reducing max points to 500 and retry

### Slow performance
- Reduce the number of selected signals (keep under 5)
- Decrease max points to 1,000 or less
- Choose a shorter time range
- Check backend query execution time in toolbar

### API connection failed
- Ensure backend is running at http://localhost:8000
- Check backend terminal for errors
- Verify Athena table exists and has data
- Check AWS credentials are configured

## 🔧 Configuration

Edit `.env.development` to customize:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_APP_TITLE=CAN Telemetry Dashboard
VITE_MAX_SIGNALS=10
VITE_DEFAULT_MAX_POINTS=2000
```

## 📈 Performance Tips

**For best performance:**
1. Select 3-5 signals max
2. Use 2,000 max points for real-time feel
3. Stick to preset time ranges (avoid custom 30-day queries)
4. Close the legend if not needed (more screen space)
5. Use CSV export for detailed analysis instead of max points

**For detailed analysis:**
1. Select 1-2 signals only
2. Increase max points to 10,000+
3. Export CSV for Excel/Python analysis
4. Use zoom to inspect specific time windows

## 🎯 Next Steps

The dashboard is now fully functional! You can:

1. **Test the full workflow** with your real CAN data
2. **Customize styling** in `tailwind.config.ts`
3. **Add more features** like:
   - Real-time WebSocket updates
   - Saved query configurations
   - Multi-vehicle comparison
   - Threshold-based alerts
   - Annotations on charts
4. **Deploy to production** via AWS CloudFront

## 📝 File Structure

```
frontend/
├── src/
│   ├── api/                  # API layer
│   │   ├── types.ts
│   │   ├── client.ts
│   │   └── hooks.ts
│   ├── store/                # State management
│   │   ├── selectionStore.ts
│   │   └── chartStore.ts
│   ├── utils/                # Utility functions
│   │   ├── colors.ts
│   │   ├── formatters.ts
│   │   ├── timeRanges.ts
│   │   └── chartHelpers.ts
│   ├── components/
│   │   ├── common/          # Reusable components
│   │   ├── layout/          # Layout structure
│   │   ├── selectors/       # Data selection controls
│   │   └── chart/           # Chart components
│   ├── App.tsx              # Main dashboard
│   └── main.tsx             # Entry point
├── package.json
├── vite.config.ts
├── tailwind.config.ts
└── .env.development
```

Happy visualizing! 🚀📊
