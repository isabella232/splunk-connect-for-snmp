from unittest import TestCase, mock
from unittest.mock import Mock, patch

from splunk_connect_for_snmp.common.inventory_record import InventoryRecord
from splunk_connect_for_snmp.inventory.tasks import (
    generate_poll_task_definition,
    inventory_setup_poller,
)


class TestInventorySetupPoller(TestCase):
    @mock.patch("splunk_connect_for_snmp.common.profiles.load_profiles")
    @patch("splunk_connect_for_snmp.customtaskmanager.CustomPeriodicTaskManager")
    @mock.patch("pymongo.collection.Collection.find_one")
    @mock.patch("splunk_connect_for_snmp.inventory.tasks.assign_profiles")
    @mock.patch("splunk_connect_for_snmp.inventory.tasks.get_inventory")
    def test_inventory_setup_poller(
        self,
        m_get_inventory,
        m_assign_profiles,
        m_find_one,
        m_task_manager,
        m_load_profiles,
    ):
        periodic_obj_mock = Mock()
        m_task_manager.return_value = periodic_obj_mock

        m_get_inventory.return_value = InventoryRecord.from_dict(
            {
                "address": "192.168.0.1",
                "port": "34",
                "version": "2c",
                "community": "public",
                "secret": "secret",
                "securityEngine": "ENGINE",
                "walk_interval": 1850,
                "profiles": "",
                "SmartProfiles": True,
                "delete": False,
            }
        )

        m_find_one.return_value = {
            "state": {
                "SNMPv2-MIB|sysDescr": {"value": "MIKROTIK"},
                "SNMPv2-MIB|sysName": {"value": "Linux Debian 2.0.1"},
                "SNMPv2-MIB|sysContact": {"value": "non-existing-name@splunk"},
            }
        }

        work = {"address": "192.168.0.1"}

        m_assign_profiles.return_value = {
            60: ["BaseUpTime"],
            30: ["profile5", "profile2"],
            20: ["profile1"],
        }

        # when
        inventory_setup_poller(work)

        m_load_profiles.assert_not_called()

        calls = periodic_obj_mock.manage_task.call_args_list

        self.assertEqual(
            {"address": "192.168.0.1", "profiles": {"BaseUpTime"}, "frequency": 60},
            calls[0][1]["kwargs"],
        )
        self.assertEqual(
            {
                "address": "192.168.0.1",
                "profiles": {"profile2", "profile5"},
                "frequency": 30,
            },
            calls[1][1]["kwargs"],
        )
        self.assertEqual(
            {"address": "192.168.0.1", "profiles": {"profile1"}, "frequency": 20},
            calls[2][1]["kwargs"],
        )

        periodic_obj_mock.delete_unused_poll_tasks.assert_called_with(
            "192.168.0.1",
            [
                "sc4snmp;192.168.0.1;60;poll",
                "sc4snmp;192.168.0.1;30;poll",
                "sc4snmp;192.168.0.1;20;poll",
            ],
        )
        periodic_obj_mock.delete_disabled_poll_tasks.assert_called()

    def test_generate_poll_task_definition(self):
        active_schedules = []
        address = "192.168.0.1"
        assigned_profiles = {
            60: ["BaseUpTime"],
            30: ["profile5", "profile2"],
            20: ["profile1"],
        }
        period = 30

        result = generate_poll_task_definition(
            active_schedules, address, assigned_profiles, period
        )

        self.assertEqual("sc4snmp;192.168.0.1;30;poll", result["name"])
        self.assertEqual("splunk_connect_for_snmp.snmp.tasks.poll", result["task"])
        self.assertEqual("192.168.0.1", result["target"])
        self.assertEqual([], result["args"])
        self.assertEqual(
            {
                "address": "192.168.0.1",
                "profiles": {"profile2", "profile5"},
                "frequency": 30,
            },
            result["kwargs"],
        )
        self.assertEqual(
            "splunk_connect_for_snmp.enrich.tasks.enrich",
            result["options"]["link"].tasks[0].name,
        )
        self.assertEqual(
            "splunk_connect_for_snmp.splunk.tasks.prepare",
            result["options"]["link"].tasks[1].name,
        )
        self.assertEqual(
            "splunk_connect_for_snmp.splunk.tasks.send",
            result["options"]["link"].tasks[2].name,
        )
        self.assertEqual({"every": 30, "period": "seconds"}, result["interval"])
        self.assertEqual(True, result["enabled"])
        self.assertEqual(False, result["run_immediately"])

        self.assertEqual("sc4snmp;192.168.0.1;30;poll", active_schedules[0])
