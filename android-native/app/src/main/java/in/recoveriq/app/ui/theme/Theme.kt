package `in`.recoveriq.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val BrandBlue = Color(0xFF1E62D0)
val BrandBlueDark = Color(0xFF1748A0)
val Surface = Color(0xFFF4F7FB)
val CardWhite = Color(0xFFFFFFFF)
val TextDark = Color(0xFF10233F)
val Muted = Color(0xFF5B6B84)
val Good = Color(0xFF15A66A)
val Warn = Color(0xFFE0A800)
val Bad = Color(0xFFDC3545)

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
