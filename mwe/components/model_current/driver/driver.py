import datetime

import icon4py.model.common.utils as common_utils

from model_current.atmosphere.dycore import dycore_states
from model_current.common.io import io as common_io
from model_current.common.states import (
    prognostic_state as prognostics,
    tracer_prep_adv_states as prep_adv_states,
    tracer_states,
)
from model_current.driver import driver_io, driver_states, driver_utils


class Icon4pyDriver:
    def __init__(
        self,
        *,
        granules: driver_utils.Granules,
        model_time_variables: driver_states.ModelTimeVariables,
        io_monitor: common_io.IOMonitor,
    ) -> None:
        self.io_monitor = io_monitor
        self.granules = granules
        self.model_time_variables = model_time_variables
        self._diagnostics_computer = driver_io.DiagnosticsComputer()

    def _is_last_substep(self, step_nr: int) -> bool:
        return step_nr == (self.model_time_variables.ndyn_substeps_var - 1)

    @staticmethod
    def _is_first_substep(step_nr: int) -> bool:
        return step_nr == 0

    def _store_output(
        self,
        prognostic_state: prognostics.PrognosticState,
        simulation_current_datetime: datetime.datetime,
    ) -> None:
        state_to_store = driver_io.prognostic_state_to_dataarrays(prognostic_state)
        state_to_store.update(self._diagnostics_computer.compute(prognostic_state))
        self.io_monitor.store(state_to_store, simulation_current_datetime)

    def time_integration(self, ds: driver_states.DriverStates) -> None:
        prognostic_states = ds.prognostics
        tracers = ds.tracers
        prep_adv = ds.prep_advection_prognostic
        tracer_prep_adv = ds.prep_tracer_advection_prognostic
        for time_step in range(self.model_time_variables.n_time_steps):
            self.model_time_variables.advance_simulation_datetime()
            self._integrate_one_time_step(
                prognostic_states=prognostic_states,
                tracers=tracers,
                prep_adv=prep_adv,
                tracer_prep_adv=tracer_prep_adv,
            )
            self._store_output(prognostic_states.current, self.model_time_variables.simulation_current_datetime)

    def _integrate_one_time_step(
        self,
        *,
        prognostic_states: common_utils.TimeStepPair[prognostics.PrognosticState],
        tracers: common_utils.TimeStepPair[tracer_states.TracerState],
        prep_adv: dycore_states.PrepAdvection,
        tracer_prep_adv: prep_adv_states.TracerPrepAdvState,
    ) -> None:
        self._do_dyn_substepping(prognostic_states, prep_adv)
        self.granules.diffusion.run(prognostic_states.next, self.model_time_variables.dtime_in_seconds)
        for tracer_current in tracers.current.active_fields():
            tracer_next_field = getattr(tracers.next, tracer_current.name)
            self.granules.tracer_advection.run(
                prep_adv=tracer_prep_adv,
                p_tracer_now=tracer_current.field,
                p_tracer_new=tracer_next_field,
                dtime=self.model_time_variables.dtime_in_seconds,
            )
        self.granules.physics.run(
            prognostic=prognostic_states.next,
            tracers=tracers.next,
            dtime=self.model_time_variables.dtime,
            simulation_current_datetime=self.model_time_variables.simulation_current_datetime,
        )
        prognostic_states.swap()
        tracers.swap()

    def _do_dyn_substepping(
        self,
        prognostic_states: common_utils.TimeStepPair[prognostics.PrognosticState],
        prep_adv: dycore_states.PrepAdvection,
    ) -> None:
        for dyn_substep in range(self.model_time_variables.ndyn_substeps_var):
            self.granules.solve_nonhydro.time_step(
                prognostic_states=prognostic_states,
                prep_adv=prep_adv,
                dtime=self.model_time_variables.substep_timestep,
                ndyn_substeps_var=self.model_time_variables.ndyn_substeps_var,
                at_first_substep=self._is_first_substep(dyn_substep),
                at_last_substep=self._is_last_substep(dyn_substep),
            )
            if not self._is_last_substep(dyn_substep):
                prognostic_states.swap()


def initialize_driver() -> Icon4pyDriver:
    model_time_variables = driver_states.ModelTimeVariables()
    granules = driver_utils.initialize_granules(model_time_variables)
    io_monitor = common_io.IOMonitor(variables=driver_io.DEFAULT_OUTPUT_VARIABLES)
    return Icon4pyDriver(granules=granules, model_time_variables=model_time_variables, io_monitor=io_monitor)


def run_driver() -> tuple[driver_states.DriverStates, Icon4pyDriver]:
    icon4py_driver = initialize_driver()
    ds = driver_states.assemble_driver_states(
        prognostic_state_now=prognostics.initialize_prognostic_state(),
        tracer_state_now=tracer_states.initialize_tracer_state(),
        tracer_prep_adv_state=prep_adv_states.initialize_tracer_prep_adv_state(),
    )
    icon4py_driver.time_integration(ds)
    return ds, icon4py_driver
