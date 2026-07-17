# Moshi / Retrofit
-keep,allowobfuscation,allowshrinking interface retrofit2.Call
-keep,allowobfuscation,allowshrinking class retrofit2.Response
-keepclassmembers class ** {
    @com.squareup.moshi.Json <fields>;
}
-keep class in.recoveriq.app.data.** { *; }
-dontwarn okhttp3.**
-dontwarn okio.**
