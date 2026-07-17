package `in`.recoveriq.app

import android.app.Application
import `in`.recoveriq.app.data.Api
import `in`.recoveriq.app.data.Session
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class RecoverIQApp : Application() {
    override fun onCreate() {
        super.onCreate()
        // Hydrate the in-memory JWT cache as early as possible so a service restarted by
        // the OS (before any UI) can already authenticate its pings.
        CoroutineScope(Dispatchers.IO).launch {
            Api.token = Session(applicationContext).token()
        }
    }
}
