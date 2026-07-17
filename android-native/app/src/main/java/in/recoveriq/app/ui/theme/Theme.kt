package `in`.recoveriq.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Palette lifted directly from the web app's styles.css :root variables.
val BrandBlue = Color(0xFF2563EB)      // --gold
val BrandBlueLite = Color(0xFF3B82F6)  // --gold-2
val BrandBlueDark = Color(0xFF1D4ED8)  // --gold-deep
val Surface = Color(0xFFF4F7FB)        // --glass
val CardWhite = Color(0xFFFFFFFF)      // --glass-2
val TextDark = Color(0xFF0F1B2D)       // --ink
val Muted = Color(0xFF475569)          // --ink-soft
val MutedDim = Color(0xFF8494A8)       // --ink-dim
val StrokeSoft = Color(0xFFE3E9F1)     // --stroke-soft
val Good = Color(0xFF16A34A)           // --good
val Warn = Color(0xFFD97706)           // --warn
val Bad = Color(0xFFDC2626)            // --bad

private val LightColors = lightColorScheme(
    primary = BrandBlue,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFDCE8FB),
    onPrimaryContainer = BrandBlueDark,
    secondary = BrandBlueDark,
    background = Surface,
    onBackground = TextDark,
    surface = CardWhite,
    onSurface = TextDark,
    surfaceVariant = Color(0xFFEAF0F8),
    onSurfaceVariant = Muted,
    outline = StrokeSoft,
    error = Bad,
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF7EA9F0),
    onPrimary = Color(0xFF0A1B33),
    background = Color(0xFF0C1524),
    surface = Color(0xFF13203A),
    onSurface = Color(0xFFE7EEF9),
)

@Composable
fun RecoverIQTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        typography = Typography(),
        content = content,
    )
}
