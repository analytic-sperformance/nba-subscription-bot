from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_broadcast = State()


class UserStates(StatesGroup):
    waiting_for_receipt = State()
