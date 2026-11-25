import SwiftUI

// Palette lifted from Theme.kt (itself from the web app's styles.css :root variables).
// Names are identical to Kotlin: Color.BrandBlue, Color.Muted, Color.Good, Color.Bad, Color.Warn …
extension Color {
    /// ARGB hex, e.g. Color(argb: 0xFF2563EB) — same literal form as Compose `Color(0xFF2563EB)`.
    init(argb: UInt32) {
        let a = Double((argb >> 24) & 0xFF) / 255.0
        let r = Double((argb >> 16) & 0xFF) / 255.0
        let g = Double((argb >> 8) & 0xFF) / 255.0
        let b = Double(argb & 0xFF) / 255.0
        self.init(.sRGB, red: r, green: g, blue: b, opacity: a)
    }

    static let BrandBlue = Color(argb: 0xFF2563EB)      // --gold
    static let BrandBlueLite = Color(argb: 0xFF3B82F6)  // --gold-2
    static let BrandBlueDark = Color(argb: 0xFF1D4ED8)  // --gold-deep
    static let Surface = Color(argb: 0xFFF4F7FB)        // --glass
    static let CardWhite = Color(argb: 0xFFFFFFFF)      // --glass-2
    static let TextDark = Color(argb: 0xFF0F1B2D)       // --ink
    static let Ink = Color(argb: 0xFF0F1B2D)            // alias of TextDark
    static let Muted = Color(argb: 0xFF475569)          // --ink-soft
    static let MutedDim = Color(argb: 0xFF8494A8)       // --ink-dim
    static let StrokeSoft = Color(argb: 0xFFE3E9F1)     // --stroke-soft
    static let Good = Color(argb: 0xFF16A34A)           // --good
    static let Warn = Color(argb: 0xFFD97706)           // --warn
    static let Bad = Color(argb: 0xFFDC2626)            // --bad
    static let GlassStroke = Color(argb: 0x382563EB)    // --stroke rgba(37,99,235,.22)
    static let GlassTint = Color(argb: 0xCCFFFFFF)      // translucent white for glass surfaces
    static let PrimaryContainer = Color(argb: 0xFFDCE8FB)
    static let SurfaceVariant = Color(argb: 0xFFEAF0F8)
    static let TopBar = Color(argb: 0xF2FFFFFF)
    static let Scrim = Color(argb: 0xCC0B1733)
}

/// Soft light gradient behind the app (Theme.kt AppBackground).
enum AppTheme {
    static let background = LinearGradient(colors: [Color(argb: 0xFFF7FAFF), Color(argb: 0xFFEAF0FA)],
                                           startPoint: .top, endPoint: .bottom)
    // Rounded, web-like corners (--radius:16px) — Theme.kt AppShapes.
    static let radiusXS: CGFloat = 8
    static let radiusS: CGFloat = 10
    static let radiusM: CGFloat = 16
    static let radiusL: CGFloat = 20
    static let radiusXL: CGFloat = 24
}

/// Material-3 type scale names used by the Compose screens → SwiftUI fonts.
extension Font {
    static let headlineMedium = Font.system(size: 28, weight: .regular)
    static let headlineSmall = Font.system(size: 24, weight: .regular)
    static let titleLarge = Font.system(size: 22, weight: .regular)
    static let titleMedium = Font.system(size: 16, weight: .medium)
    static let titleSmall = Font.system(size: 14, weight: .medium)
    static let bodyLarge = Font.system(size: 16, weight: .regular)
    static let bodyMedium = Font.system(size: 14, weight: .regular)
    static let bodySmall = Font.system(size: 12, weight: .regular)
    static let labelLarge = Font.system(size: 14, weight: .medium)
    static let labelMedium = Font.system(size: 12, weight: .medium)
    static let labelSmall = Font.system(size: 11, weight: .medium)
}

/// App background modifier: `.appBackground()`.
extension View {
    func appBackground() -> some View {
        self.background(AppTheme.background.ignoresSafeArea())
    }
}
