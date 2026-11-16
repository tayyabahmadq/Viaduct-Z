package com.viaduct.pay

import com.viaduct.pay.utils.AccountState
import com.viaduct.pay.utils.GuardDecision
import com.viaduct.pay.utils.TxDraft
import com.viaduct.pay.utils.TxGuard
import kotlinx.serialization.Serializable
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Runs the same fixtures as `server/tests/test_guard.py`.
 *
 * `android/app/build.gradle.kts` adds the repo-root `fixtures/` folder to the
 * unit-test resources, so there is exactly one copy of the expectations.
 */
class TxGuardTest {

    private val json = Json { ignoreUnknownKeys = true }

    @Serializable
    private data class Fixture(
        val name: String,
        val tx: TxDraft,
        val state: AccountState,
        val expected: GuardDecision
    )

    private val fixtures: List<Fixture> by lazy {
        val stream = TxGuardTest::class.java.classLoader
            ?.getResourceAsStream("guard_fixtures.json")
            ?: error("guard_fixtures.json missing from unit-test resources")
        json.decodeFromString<List<Fixture>>(stream.readBytes().decodeToString())
    }

    @Test
    fun fixturesArePresent() {
        // The canonical 30 are frozen; scripts/gen_fixtures.py only appends.
        assertTrue("expected at least the 30 canonical fixtures", fixtures.size >= 30)
    }

    @Test
    fun everyFixtureMatches() {
        fixtures.forEach { fixture ->
            assertEquals(
                fixture.name,
                fixture.expected,
                TxGuard.screen(fixture.tx, fixture.state)
            )
        }
    }
}
