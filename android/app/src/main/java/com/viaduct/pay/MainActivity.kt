package com.viaduct.pay

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.viaduct.pay.data.LocalStorage
import com.viaduct.pay.ui.AssistantScreen
import com.viaduct.pay.ui.HistoryScreen
import com.viaduct.pay.ui.HomeScreen
import com.viaduct.pay.ui.ProfileScreen
import com.viaduct.pay.ui.RegisterScreen
import com.viaduct.pay.ui.ScanScreen
import com.viaduct.pay.ui.SendScreen
import com.viaduct.pay.ui.TopUpScreen

private val LightColors = lightColorScheme(
    primary = Color(0xFF2563EB),
    background = Color(0xFFF8FAFC),
    surface = Color(0xFFFFFFFF)
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF3B82F6),
    background = Color(0xFF09090B),
    surface = Color(0xFF101013)
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        LocalStorage.init(this)

        setContent {
            MaterialTheme(
                colorScheme = if (isSystemInDarkTheme()) DarkColors else LightColors
            ) {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    AppRoot()
                }
            }
        }
    }
}

@Composable
private fun AppRoot() {
    val nav = rememberNavController()
    val start = remember { if (LocalStorage.account == null) "register" else "home" }

    NavHost(navController = nav, startDestination = start) {
        composable("register") { RegisterScreen(nav) }
        composable("home") { HomeScreen(nav) }
        composable("scan") { ScanScreen(nav) }
        composable(
            "send/{token48}/{label}?amount={amount}",
            arguments = listOf(
                navArgument("amount") {
                    type = NavType.IntType
                    defaultValue = 0
                }
            )
        ) { entry ->
            SendScreen(
                nav = nav,
                token48 = entry.arguments?.getString("token48").orEmpty(),
                label = entry.arguments?.getString("label").orEmpty(),
                initialAmountCents = entry.arguments?.getInt("amount") ?: 0
            )
        }
        composable("history") { HistoryScreen(nav) }
        composable("profile") { ProfileScreen(nav) }
        composable("topup") { TopUpScreen(nav) }
        composable("assistant") { AssistantScreen(nav) }
    }
}
