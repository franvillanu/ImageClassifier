# Color Difference Diagnosis Guide

If you're experiencing color differences between fullscreen and maximized window modes, this guide helps diagnose the cause.

## Quick Checks

### 1. Check Windows Color Profile

1. Right-click desktop → **Display settings**
2. Scroll down → **Advanced display settings**
3. Click **Display adapter properties**
4. Go to **Color Management** tab
5. Check what **ICC profile** is assigned to your display

**What to look for:**
- If it's NOT "sRGB IEC61966-2.1" or a generic profile, Windows is applying color management
- Different profiles can cause color shifts between fullscreen and windowed modes

### 2. Check Monitor Hardware Settings

**On your monitor's OSD (On-Screen Display):**
- Look for **Color Mode** or **Picture Mode** settings
- Common modes: sRGB, Adobe RGB, DCI-P3, Custom, etc.
- Some monitors apply different color processing in different modes
- Try switching to **sRGB mode** if available

**Other monitor settings to check:**
- **Brightness/Contrast** - Should be consistent
- **Color Temperature** - Should match between modes
- **Gamma** - Should be consistent
- **HDR** - If enabled, can cause color differences

### 3. Check Graphics Driver Settings

**NVIDIA:**
1. Right-click desktop → **NVIDIA Control Panel**
2. **Display** → **Change resolution**
3. Check **Color settings** - Look for "Output color format" and "Output color depth"
4. **Display** → **Adjust desktop color settings** - Check if any color adjustments are applied

**AMD:**
1. Right-click desktop → **AMD Radeon Software**
2. **Display** tab
3. Check **Color** settings - Look for color temperature, saturation, etc.

**Intel:**
1. Right-click desktop → **Intel Graphics Settings**
2. **Display** → **Color Settings**
3. Check for any color adjustments

### 4. Test with Other Applications

Try fullscreen in other image viewers:
- **Windows Photos** app
- **IrfanView** (if installed)
- **VLC Media Player** (for video/images)

**If other apps show the same issue:**
- It's likely a Windows/monitor/driver issue, not the application

**If only Image Classifier shows the issue:**
- It's likely application-specific (Qt/OpenGL color management)

### 5. Check Windows Color Management Service

1. Press `Win + R` → type `services.msc`
2. Find **Windows Color System** service
3. Check if it's running
4. Try restarting it: Right-click → **Restart**

### 6. Monitor-Specific Issues

Some monitors have known issues:
- **Gaming monitors** with "overdrive" or "response time" settings may apply different processing
- **HDR monitors** may switch color spaces when going fullscreen
- **Multi-monitor setups** - Each monitor may have different color profiles

## Solutions to Try

### Solution 1: Set sRGB Color Profile

1. Go to **Color Management** (see step 1 above)
2. Click **Add...**
3. Select **sRGB IEC61966-2.1**
4. Set as **Default**
5. Restart the application

### Solution 2: Disable Windows Color Management (Advanced)

⚠️ **Warning:** This affects all applications

1. In **Color Management**, remove all profiles except sRGB
2. Or use registry edit (not recommended unless you know what you're doing)

### Solution 3: Monitor Hardware Reset

1. Use monitor's OSD menu
2. Find **Reset** or **Factory Reset** option
3. Then manually configure to sRGB mode if available

### Solution 4: Graphics Driver Reset

1. Reset graphics driver to defaults
2. Disable any color enhancements
3. Set output to sRGB if available

## Is It Your Monitor?

**Signs it might be monitor-related:**
- ✅ Color difference appears in other fullscreen applications too
- ✅ Monitor has multiple color modes (sRGB, Adobe RGB, etc.)
- ✅ Monitor is HDR-capable
- ✅ Color difference is consistent and reproducible
- ✅ Changing monitor settings affects the difference

**Signs it might be Windows/driver-related:**
- ✅ Windows has a custom ICC profile assigned
- ✅ Graphics driver has color adjustments enabled
- ✅ Issue appears on multiple monitors
- ✅ Color difference varies by application

**Signs it might be application-specific:**
- ✅ Only Image Classifier shows the issue
- ✅ Other Qt/OpenGL apps show similar issues
- ✅ Issue persists across different monitors

## Reporting the Issue

If you want to report this, please include:
1. Monitor model and brand
2. Graphics card model and driver version
3. Windows version (Win 10/11, build number)
4. Whether other apps show the same issue
5. What color profile Windows is using
6. Monitor's color mode setting
