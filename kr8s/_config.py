# SPDX-FileCopyrightText: Copyright (c) 2024, Kr8s Developers (See LICENSE for list)
# SPDX-License-Identifier: BSD 3-Clause License
from typing import Dict, List

import anyio
import yaml

from kr8s._data_utils import dict_list_pack, list_dict_unpack

# TODO Implement set
# TODO Implement unset
# TODO Implement set cluster
# TODO Implement delete cluster
# TODO Implement set context
# TODO Implement delete context
# TODO Implement set user
# TODO Implement delete user


class KubeConfigSet(object):
    def __init__(self, *kubeconfigs):
        if isinstance(kubeconfigs, dict):
            self_configs[KubeConfig(kubeconfig)]
        else:
            self._configs = [KubeConfig(kubeconfig) for kubeconfig in kubeconfigs]

    def __await__(self):
        async def f():
            for config in self._configs:
                await config
            return self

        return f().__await__()

    async def save(self):
        for config in self._configs:
            await config.save()

    @property
    def path(self) -> str:
        return self.get_path()

    def get_path(self, context: str = None) -> str:
        """Return the path of the config for the current context.

        Args:
            context (str): Override the context to use. If not provided, the current context is used.
        """
        if not context:
            context = self.current_context
        if context:
            for config in self._configs:
                if context in [c["name"] for c in config.contexts]:
                    return config.path
        return self._configs[0].path

    @property
    def raw(self) -> Dict:
        """Merge all kubeconfig data into a single kubeconfig."""
        data = {
            "apiVersion": "v1",
            "kind": "Config",
            "preferences": self.preferences,
            "clusters": self.clusters,
            "users": self.users,
            "contexts": self.contexts,
            "current-context": self.current_context,
        }
        if self.extensions:
            data["extensions"] = self.extensions
        return data

    @property
    def current_context(self) -> str:
        """Return the current context from the first kubeconfig.

        Context configuration from multiples files are ignored.
        """
        return self._configs[0].current_context

    @property
    def current_namespace(self) -> str:
        """Return the current namespace from the current context."""
        return self.get_context(self.current_context).get("namespace", "default")

    async def use_namespace(self, namespace: str) -> None:
        for config in self._configs:
            for context in config._raw["contexts"]:
                if context["name"] == self.current_context:
                    context["context"]["namespace"] = namespace
            await config.save()

    async def use_context(self, context: str) -> None:
        """Set the current context."""
        if context not in [c["name"] for c in self.contexts]:
            raise ValueError(f"Context {context} not found")
        await self._configs[0].use_context(context, allow_unknown=True)

    async def rename_context(self, old: str, new: str) -> None:
        """Rename a context."""
        for config in self._configs:
            if old in [c["name"] for c in config.contexts]:
                await config.rename_context(old, new)
                if self.current_context == old:
                    await self.use_context(new)
                return
        raise ValueError(f"Context {old} not found")

    def get_context(self, context_name: str) -> Dict:
        """Get a context by name."""
        for context in self.contexts:
            if context["name"] == context_name:
                return context["context"]
        raise ValueError(f"Context {context_name} not found")

    def get_cluster(self, cluster_name: str) -> Dict:
        """Get a cluster by name."""
        for cluster in self.clusters:
            if cluster["name"] == cluster_name:
                return cluster["cluster"]
        raise ValueError(f"Cluster {cluster_name} not found")

    def get_user(self, user_name: str) -> Dict:
        """Get a user by name."""
        for user in self.users:
            if user["name"] == user_name:
                return user["user"]
        raise ValueError(f"User {user_name} not found")

    @property
    def preferences(self) -> Dict:
        return self._configs[0].preferences

    @property
    def clusters(self) -> List[Dict]:
        clusters = [cluster for config in self._configs for cluster in config.clusters]
        # Unpack and repack to remove duplicates
        clusters = list_dict_unpack(clusters, "name", "cluster")
        clusters = dict_list_pack(clusters, "name", "cluster")
        return clusters

    @property
    def users(self) -> List[Dict]:
        users = [user for config in self._configs for user in config.users]
        # Unpack and repack to remove duplicates
        users = list_dict_unpack(users, "name", "user")
        users = dict_list_pack(users, "name", "user")
        return users

    @property
    def contexts(self) -> List[Dict]:
        contexts = [context for config in self._configs for context in config.contexts]
        # Unpack and repack to remove duplicates
        contexts = list_dict_unpack(contexts, "name", "context")
        contexts = dict_list_pack(contexts, "name", "context")
        return contexts

    @property
    def extensions(self) -> List[Dict]:
        return [
            extension for config in self._configs for extension in config.extensions
        ]


class KubeConfig(object):
    def __init__(self, path, raw):
        self.path = path
        self._raw = raw
        self.__write_lock = anyio.Lock()

    def __await__(self):
        async def f():
            if not self._raw:
                async with await anyio.open_file(self.path) as fh:
                    self._raw = yaml.safe_load(await fh.read())
            return self

        return f().__await__()

    async def save(self) -> None:
        if not self._raw:
            async with self.__write_lock:
                async with await anyio.open_file(self.path, "w") as fh:
                    await fh.write(yaml.safe_dump(self._raw))

    @property
    def current_context(self) -> str:
        return self._raw["current-context"]

    @property
    def current_namespace(self) -> str:
        return self.get_context(self.current_context).get("namespace", "default")

    async def use_namespace(self, namespace: str) -> None:
        for context in self._raw["contexts"]:
            if context["name"] == self.current_context:
                context["context"]["namespace"] = namespace
        await self.save()

    async def use_context(self, context: str, allow_unknown: bool = False) -> None:
        """Set the current context."""
        if not allow_unknown and context not in [c["name"] for c in self.contexts]:
            raise ValueError(f"Context {context} not found")
        self._raw["current-context"] = context
        await self.save()

    async def rename_context(self, old: str, new: str) -> None:
        """Rename a context."""
        for context in self._raw["contexts"]:
            if context["name"] == old:
                context["name"] = new
                if self.current_context == old:
                    await self.use_context(new)
                await self.save()
                return
        raise ValueError(f"Context {old} not found")

    def get_context(self, context_name: str) -> Dict:
        """Get a context by name."""
        for context in self.contexts:
            if context["name"] == context_name:
                return context["context"]
        raise ValueError(f"Context {context_name} not found")

    def get_cluster(self, cluster_name: str) -> Dict:
        """Get a cluster by name."""
        for cluster in self.clusters:
            if cluster["name"] == cluster_name:
                return cluster["cluster"]
        raise ValueError(f"Cluster {cluster_name} not found")

    def get_user(self, user_name: str) -> Dict:
        """Get a user by name."""
        for user in self.users:
            if user["name"] == user_name:
                return user["user"]
        raise ValueError(f"User {user_name} not found")

    @property
    def raw(self) -> Dict:
        return self._raw

    @property
    def preferences(self) -> List[Dict]:
        return self._raw["preferences"]

    @property
    def clusters(self) -> List[Dict]:
        return self._raw["clusters"]

    @property
    def users(self) -> List[Dict]:
        return self._raw["users"]

    @property
    def contexts(self) -> List[Dict]:
        return self._raw["contexts"]

    @property
    def extensions(self) -> List[Dict]:
        return self._raw["extensions"] if "extensions" in self._raw else []
